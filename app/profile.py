from dataclasses import dataclass


@dataclass(frozen=True)
class RecognitionProfile:
    previews: bool
    end_silence_ms: int
    clip_seconds: float
    queue_size: int
    beam_size: int
    max_caption_age: float | None


PROFILES = (
    RecognitionProfile(True, 300, 3.2, 4, 1, 4),
    RecognitionProfile(True, 360, 4.0, 6, 1, 6),
    RecognitionProfile(False, 480, 5.5, 12, 2, 12),
    RecognitionProfile(False, 650, 7.5, 24, 3, None),
    RecognitionProfile(False, 850, 10, 48, 5, None),
)
DEFAULT_PROFILE = 1


def recognition_profile(settings):
    return PROFILES[max(0, min(len(PROFILES) - 1, int(settings.get("recognition_profile", DEFAULT_PROFILE))))]
