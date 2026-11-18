# SubtitleForEveryone

Sottotitoli in tempo reale per persone sorde o ipoacusiche su Windows 11 x64. Puoi sottotitolare l’audio di Windows, per esempio un film riprodotto nel browser.

## Installazione da sorgente

Installa Python 3.12 x64 con il launcher `py` e Visual Studio Build Tools con C++ desktop e Windows SDK. Da PowerShell esegui `.\setup_windows.ps1` per installare le dipendenze e compilare il componente audio, quindi avvia `run_windows.bat`.

## Uso

1. **Tutto l’audio delle app** cattura il parlato riprodotto dalle applicazioni Windows anche se usano uscite diverse. Per ascoltare una singola app, seleziona il processo o digita il nome, ad esempio `chrome.exe`.
2. Premi **Avvia**. Whisper rileva automaticamente la lingua parlata. In **Lingua dei sottotitoli** puoi mantenere l’originale o tradurre in italiano, inglese, spagnolo, francese o tedesco. La prima volta servono Internet e i modelli della coppia linguistica. Riconoscimento e traduzione avvengono in locale.
3. Trascina l’area del testo per spostare la finestra e usa l’angolo inferiore destro per ridimensionarla. Dal pannello principale puoi scegliere il font, il colore e la dimensione del testo, regolare l’opacità, impostare la priorità in primo piano e riattivare la barra del titolo.
4. Il **Monitor sottotitoli** mostra l’ultima frase in tempo reale. **Prova sottotitoli** visualizza un esempio anche con la trascrizione in pausa. Per i video a schermo intero, usa la modalità finestra senza bordi se il player in modalità esclusiva copre i sottotitoli.
5. La **X** del pannello principale lo nasconde nell’area di notifica. Dall’icona puoi riaprire il pannello, avviare o mettere in pausa la trascrizione, mostrare o nascondere i sottotitoli e uscire.

## Accelerazione GPU

- **CUDA** richiede una GPU NVIDIA con driver aggiornati. Dopo l’installazione esegui `.\setup_cuda.ps1` e scegli la tua GPU CUDA in **Elaborazione**.
- **Vulkan** richiede un driver Vulkan, `vulkaninfo` e un server whisper.cpp compilato con Vulkan. Esegui `.\setup_vulkan.ps1 -Model tiny -GpuIndex 1`, sostituendo modello e indice con quelli scelti in **Elaborazione**. Per compilare il server lo script usa Visual Studio 2022 Build Tools con C++, CMake, Ninja e Vulkan SDK. Se disponi già di un server compilato, metti `whisper-server.exe` nella cartella `whisper-vulkan` prima di eseguire lo script.
- Lo stato mostra il backend in uso. In caso di errore GPU, l’app riprova con CPU INT8.

Il modello `tiny` è il più rapido. `base`, `small`, `medium` e `large-v3` richiedono progressivamente più risorse. Per provare `large-v3` con Vulkan usa `.\setup_vulkan.ps1 -Model large-v3 -GpuIndex 1` con l’indice della tua GPU. La qualità dipende da lingua, rumore e chiarezza delle voci. La cattura di un browser può includere l’audio delle altre schede dello stesso processo.

Questo progetto deriva da [SubtitleForStream](https://github.com/tonythewizard/SubtitleForStream) ed è distribuito con licenza [GPL-3.0-only](LICENSE).
