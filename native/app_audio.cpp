#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <audioclientactivationparams.h>
#include <wrl/implements.h>
#include <wrl/client.h>
#include <cstdio>
#include <cwchar>
#include <vector>

using namespace Microsoft::WRL;

class Activation final : public RuntimeClass<RuntimeClassFlags<ClassicCom>,
                                              IActivateAudioInterfaceCompletionHandler, FtmBase> {
public:
    HANDLE ready = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    HRESULT result = E_FAIL;
    ComPtr<IAudioClient> client;

    ~Activation() { if (ready) CloseHandle(ready); }

    HRESULT STDMETHODCALLTYPE ActivateCompleted(IActivateAudioInterfaceAsyncOperation* operation) override {
        HRESULT activated = E_FAIL;
        ComPtr<IUnknown> interface_pointer;
        result = operation->GetActivateResult(&activated, &interface_pointer);
        if (SUCCEEDED(result)) result = activated;
        if (SUCCEEDED(result)) result = interface_pointer.As(&client);
        SetEvent(ready);
        return S_OK;
    }
};

static HRESULT capture(DWORD excluded_pid) {
    auto activation = Make<Activation>();
    if (!activation || !activation->ready) return E_OUTOFMEMORY;
    AUDIOCLIENT_ACTIVATION_PARAMS parameters{};
    parameters.ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK;
    parameters.ProcessLoopbackParams.TargetProcessId = excluded_pid;
    parameters.ProcessLoopbackParams.ProcessLoopbackMode = PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE;
    PROPVARIANT properties{};
    properties.vt = VT_BLOB;
    properties.blob.cbSize = sizeof(parameters);
    properties.blob.pBlobData = reinterpret_cast<BYTE*>(&parameters);
    ComPtr<IActivateAudioInterfaceAsyncOperation> operation;
    HRESULT result = ActivateAudioInterfaceAsync(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
        __uuidof(IAudioClient), &properties, activation.Get(), &operation);
    if (FAILED(result)) return result;
    if (WaitForSingleObject(activation->ready, 5000) != WAIT_OBJECT_0) return HRESULT_FROM_WIN32(ERROR_TIMEOUT);
    if (FAILED(activation->result)) return activation->result;

    auto client = activation->client;
    WAVEFORMATEX format{};
    format.wFormatTag = WAVE_FORMAT_PCM;
    format.nChannels = 2;
    format.nSamplesPerSec = 44100;
    format.wBitsPerSample = 16;
    format.nBlockAlign = format.nChannels * sizeof(short);
    format.nAvgBytesPerSec = format.nSamplesPerSec * format.nBlockAlign;
    result = client->Initialize(AUDCLNT_SHAREMODE_SHARED,
        AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM, 0, 0, &format, nullptr);
    if (FAILED(result)) return result;
    ComPtr<IAudioCaptureClient> input;
    result = client->GetService(IID_PPV_ARGS(&input));
    if (FAILED(result)) return result;
    result = client->Start();
    if (FAILED(result)) return result;

    HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
    std::vector<float> normalized;
    for (;;) {
        UINT32 frames = 0;
        result = input->GetNextPacketSize(&frames);
        if (FAILED(result)) return result;
        if (!frames) {
            Sleep(5);
            continue;
        }
        BYTE* data = nullptr;
        DWORD flags = 0;
        result = input->GetBuffer(&data, &frames, &flags, nullptr, nullptr);
        if (FAILED(result)) return result;
        normalized.resize(frames * format.nChannels);
        const auto* samples = reinterpret_cast<const short*>(data);
        for (size_t i = 0; i < normalized.size(); ++i) {
            normalized[i] = flags & AUDCLNT_BUFFERFLAGS_SILENT ? 0.0f : samples[i] / 32768.0f;
        }
        result = input->ReleaseBuffer(frames);
        if (FAILED(result)) return result;
        DWORD written = 0;
        const auto bytes = static_cast<DWORD>(normalized.size() * sizeof(float));
        if (!WriteFile(output, normalized.data(), bytes, &written, nullptr)) return S_OK;
        if (written != bytes) return HRESULT_FROM_WIN32(ERROR_WRITE_FAULT);
    }
}

int wmain(int argc, wchar_t** argv) {
    if (argc != 2) return 2;
    wchar_t* end = nullptr;
    DWORD excluded_pid = std::wcstoul(argv[1], &end, 10);
    if (!excluded_pid || *end) return 2;
    HRESULT result = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (SUCCEEDED(result)) {
        result = capture(excluded_pid);
        CoUninitialize();
    }
    if (FAILED(result)) {
        std::fprintf(stderr, "WASAPI: 0x%08lX\n", static_cast<unsigned long>(result));
        return 1;
    }
    return 0;
}
