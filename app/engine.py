"""Low-latency ASR with defensive silence/hallucination filtering.

The model is warmed when Start is pressed, not on the first utterance.
Clips are short, sources share a bounded queue and old clips are discarded
rather than being shown many seconds after the speaker stopped talking.
"""
from __future__ import annotations
from threading import Thread, Event
from queue import Queue, Empty
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from functools import partial
import sysconfig
from .hallucinations import clean_asr_text, accept_segment
from .i18n import text
from .profile import recognition_profile
from .models import ct2_model
from .cuda_runtime import ensure as ensure_cuda_runtime
from .translation import Translator
from .vulkan import VulkanWhisper

_cuda_dll_handles = []


def _load_cuda_dll_paths(runtime=()):
    if os.name != 'nt' or _cuda_dll_handles:
        return
    entries = {Path(entry).resolve() for entry in [sysconfig.get_path('purelib'), *sys.path]}
    directories = list(runtime)
    for entry in sorted(entries):
        for package in ('cublas', 'cudnn', 'cuda_nvrtc'):
            directory = entry / 'nvidia' / package / 'bin'
            if directory.is_dir():
                directories.append(directory)
    for directory in directories:
        _cuda_dll_handles.append(os.add_dll_directory(str(directory)))
        os.environ['PATH'] = str(directory) + os.pathsep + os.environ.get('PATH', '')


def nvidia_gpus():
    """Return visible NVIDIA GPUs as (index, name, memory_mb)."""
    exe = shutil.which('nvidia-smi')
    if not exe:
        try:
            from ctranslate2 import get_cuda_device_count
            return [(index, f"NVIDIA GPU {index}", 0) for index in range(get_cuda_device_count())]
        except (RuntimeError, OSError, ImportError):
            return []
    try:
        raw = subprocess.check_output(
            [exe, '--query-gpu=index,name,memory.total', '--format=csv,noheader,nounits'],
            text=True, stderr=subprocess.STDOUT, timeout=2,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        result = []
        for line in raw.splitlines():
            parts = [p.strip() for p in line.split(',', 2)]
            if len(parts) == 3:
                result.append((int(parts[0]), parts[1], int(float(parts[2]))))
        return result
    except Exception:
        return []


def _payload(item):
    """Tolerate original two-tuple for a clean upgrade from v0.1."""
    if len(item) == 2:
        source, audio = item
        return source, audio, time.monotonic()
    return item


def _word_key(word):
    return re.sub(r'^\W+|\W+$', '', word.casefold())


def _without_overlap(words, previous):
    for count in range(min(5,len(words),len(previous)),0,-1):
        if list(map(_word_key,previous[-count:]))==list(map(_word_key,words[:count])):
            return words[count:]
    return words


class ASRWorker(Thread):
    def __init__(self, settings, clips:Queue, state, logs, on_state=None, tr=None):
        super().__init__(daemon=True, name='whisper-inference')
        self.settings=settings; self.clips=clips; self.state=state; self.logs=logs
        self.tr = tr or partial(text, "en")
        self.stop_event=Event()
        self.decoding=Event()
        self.vulkan=None
        self.on_state=on_state
        self.active_device=None
        self.active_model=None
        self.selected_device=None

    def report_state(self, stage):
        if self.on_state and not self.stop_event.is_set():
            self.on_state(self,stage)

    @staticmethod
    def _binary_corrupt(error):
        message=str(error).lower()
        return 'model.bin' in message and ('is incomplete' in message or 'invalid string length' in message)

    def _create_model(self, key):
        size, requested_device = key
        if requested_device.startswith('vulkan:'):
            import numpy as np
            self.vulkan=VulkanWhisper(size,int(requested_device.split(':')[1]),self.stop_event,
                                       beam_size=recognition_profile(self.settings).beam_size,
                                       on_state=self.report_state)
            self.vulkan.decode(np.zeros(16000,dtype=np.float32),'en')
            self.active_device=requested_device
            return self.vulkan
        source = ct2_model(size, self.stop_event, self.report_state)
        self.report_state("loading")
        return self._load_whisper_model(size, requested_device, str(source))

    def _load_whisper_model(self,size,requested_device,source):
        from faster_whisper import WhisperModel
        kwargs={'local_files_only':True}
        if str(requested_device).startswith('cuda'):
            try:
                gpu_index = int(str(requested_device).split(':', 1)[1])
            except (ValueError, IndexError):
                gpu_index = 0
            try:
                runtime = (ensure_cuda_runtime(self.stop_event, self.report_state)
                           if getattr(sys, "frozen", False) and not _cuda_dll_handles else ())
                _load_cuda_dll_paths(runtime)
                model=WhisperModel(source, device='cuda', device_index=gpu_index,
                                   compute_type='int8_float16' if size == 'large-v3' else 'float16', **kwargs)
                import numpy as np
                # CUDA libraries can load lazily on the first actual decode.
                segments, _ = model.transcribe(
                    np.zeros(16000, dtype=np.float32), language='it',
                    beam_size=1, without_timestamps=True, max_new_tokens=1)
                list(segments)
                self.active_device=f'cuda:{gpu_index}'
                return model
            except Exception as ex:
                if self._binary_corrupt(ex):
                    raise
                self.logs(self.tr("gpu_fallback"))
        threads=max(2,min(16,os.cpu_count() or 4))
        model=WhisperModel(source,device='cpu',compute_type='int8',cpu_threads=threads,
                           num_workers=1,**kwargs)
        self.active_device='cpu'
        return model

    def _decode(self,model,audio,cfg):
        language = None
        profile = recognition_profile(cfg)
        if isinstance(model,VulkanWhisper):
            raw,detected=model.decode(audio,language)
            if cfg.get('hallucination_guard',True):raw=clean_asr_text(raw)
            return raw,detected
        result,info=model.transcribe(
            audio, language=language, task='transcribe', beam_size=profile.beam_size, best_of=1,
            condition_on_previous_text=False, vad_filter=bool(cfg.get('vad_enabled',True)),
            vad_parameters={'min_speech_duration_ms':120 if profile.previews else 80,
                            'threshold':.5 if profile.previews else .38, 'min_silence_duration_ms':160,
                            'speech_pad_ms':90 if profile.previews else 200}
                if cfg.get('vad_enabled',True) else None,
            temperature=0, word_timestamps=False,
            without_timestamps=True, no_speech_threshold=0.55,
            log_prob_threshold=-0.9,
        )
        clean=[]
        for seg in result:
            if cfg.get('hallucination_guard',True):
                if not accept_segment(seg):continue
                text=clean_asr_text(seg.text)
            else:text=seg.text.strip()
            if text:clean.append(text)
        raw=' '.join(clean).strip()
        if cfg.get('hallucination_guard',True):raw=clean_asr_text(raw)
        return raw,language or getattr(info,'language',None)

    def run(self):
        try:
            self._run()
        finally:
            self._close_vulkan()

    def _close_vulkan(self):
        if self.vulkan is not None:
            self.vulkan.close()
            self.vulkan=None

    def _run(self):
        model=None; current=None; cuda_failed=set()
        previews={}
        finalized={}
        translator = Translator()
        while not self.stop_event.is_set():
            cfg=self.settings.snapshot()
            desired=(cfg.get('asr_model','tiny'),cfg.get('asr_device','auto'))
            max_age = cfg.get("max_caption_age", recognition_profile(cfg).max_caption_age)
            if max_age is not None and desired[0] == "large-v3":
                max_age = max(max_age, 10)
            # Until automatic GPU certification is implemented, the safe
            # baseline must start independently of any GPU runtime.
            requested=(desired[0],'cpu') if desired[1]=='auto' or desired in cuda_failed else desired
            if current!=requested:
                self.selected_device=desired[1]
                self.active_device=None
                self.active_model=None
                self.report_state('loading')
                try:
                    self._close_vulkan()
                    model=self._create_model(requested)
                    current=requested
                    self.active_model=requested[0]
                    self.report_state('ready')
                except Exception as ex:
                    self.logs(self.tr("whisper_error", message=str(ex)))
                    if str(requested[1]).startswith(('cuda','vulkan:')):
                        cuda_failed.add(desired)
                        self.logs(self.tr("gpu_fallback"))
                    else:
                        self.report_state('retry')
                    self.stop_event.wait(1.0 if requested[1]!='cpu' else 5.0)
                    continue
            elif self.selected_device!=desired[1]:
                self.selected_device=desired[1]
                self.report_state('ready')
            try:item=self.clips.get(timeout=.20)
            except Empty:continue
            source,audio,captured_at=_payload(item)
            if self.stop_event.is_set():break
            if not any(s.get('id')==source.get('id') and s.get('enabled') for s in cfg.get('sources',[])):
                continue
            # Discard outdated subtitles (bounded latency > displaying every word).
            age=time.monotonic()-captured_at
            if max_age is not None and age>max_age:
                continue
            try:
                self.decoding.set()
                try:
                    raw,language=self._decode(model,audio,cfg)
                finally:
                    self.decoding.clear()
                if self.stop_event.is_set():break
                if not raw:continue
                # ASR itself can take many seconds on CPU. Never show old captions.
                lag=time.monotonic()-captured_at
                if max_age is not None and lag>max_age:
                    continue
                sid=source['id']
                window=(source.get('_window'),language)
                partial=source.get('_partial',False)
                words=raw.split()
                if source.get('_overlap') and sid in finalized:
                    previous_language,previous_words=finalized[sid]
                    if previous_language==language:
                        words=_without_overlap(words,previous_words)
                if partial:
                    old_window,previous,stable=previews.get(sid,(None,[],[]))
                    if old_window!=window:
                        previous,stable=[],[]
                    agreed=0
                    for old,new in zip(previous,words):
                        if _word_key(old)!=_word_key(new):
                            break
                        agreed+=1
                    if agreed>len(stable):
                        stable=previous[:agreed]
                    previews[sid]=(window,words,stable)
                    words=stable+words[len(stable):]
                else:
                    previews.pop(sid,None)
                    finalized[sid]=(language,words)
                text = ' '.join(words)
                target = cfg.get("subtitle_language", "auto")
                if target != "auto" and target != language:
                    if partial:
                        continue
                    preparing = False

                    def prepare_translation():
                        nonlocal preparing
                        preparing = True
                        self.report_state("translation")

                    try:
                        text = translator.translate(text, language, target, prepare_translation)
                    except Exception:
                        self.logs(self.tr("translation_error"))
                    finally:
                        if preparing:
                            self.report_state("ready")
                if not self.stop_event.is_set() and (max_age is None or time.monotonic() - captured_at <= max_age):
                    self.state.publish(text)
            except Exception as ex:
                self.logs(self.tr("whisper_error", message=str(ex)))
                if str(requested[1]).startswith(('cuda','vulkan:')):
                    cuda_failed.add(desired)
                    current=None
                    self.logs(self.tr("gpu_fallback"))

    def stop(self):self.stop_event.set()
