# SubtitleForEveryone

Sottotitoli in tempo reale per persone sorde o ipoacusiche su Windows 11 x64. Puoi sottotitolare l’audio di Windows, per esempio un film riprodotto nel browser.

## Installazione da sorgente

Installa Python 3.12 x64 con il launcher `py`. Da PowerShell, nella cartella del progetto, esegui `.\setup_windows.ps1`, quindi avvia `run_windows.bat`.

## Uso

1. **Tutto l’audio del computer** cattura il mix dell’uscita predefinita di Windows, da qualsiasi applicazione che la usa. Se un’app è assegnata a un’altra uscita o vuoi ascoltare solo quella, seleziona il processo oppure digita il nome, ad esempio `chrome.exe`.
2. Premi **Avvia**. Whisper riconosce la lingua parlata e produce sottotitoli nella stessa lingua. Il primo caricamento richiede Internet per scaricare il modello. Il riconoscimento successivo avviene localmente.
3. Trascina la barra della finestra dei sottotitoli, oppure l’area del testo a barra nascosta. Usa l’angolo inferiore destro per ridimensionarla. Dal pannello principale puoi regolare opacità, dimensione del testo, barra del titolo e priorità in primo piano.
4. Il **Monitor sottotitoli** mostra l’ultima frase in tempo reale. **Prova sottotitoli** visualizza un esempio anche con la trascrizione in pausa. Per i video a schermo intero, usa la modalità finestra senza bordi se il player in modalità esclusiva copre i sottotitoli.
5. La **X** del pannello principale lo nasconde nell’area di notifica. Dall’icona puoi riaprire il pannello, avviare o mettere in pausa la trascrizione, mostrare o nascondere i sottotitoli e uscire.

## Accelerazione GPU

- **CUDA** richiede una GPU NVIDIA con driver aggiornati. Dopo l’installazione esegui `.\setup_cuda.ps1` e scegli la tua GPU CUDA in **Elaborazione**.
- **Vulkan** richiede un driver Vulkan, `vulkaninfo` e un server whisper.cpp compilato con Vulkan. Esegui `.\setup_vulkan.ps1 -Model tiny -GpuIndex 1`, sostituendo modello e indice con quelli scelti in **Elaborazione**. Per compilare il server lo script usa Visual Studio 2022 Build Tools con C++, CMake, Ninja e Vulkan SDK. Se disponi già di un server compilato, metti `whisper-server.exe` nella cartella `whisper-vulkan` prima di eseguire lo script.
- Lo stato mostra il backend in uso. In caso di errore GPU, l’app riprova con CPU INT8.

Il modello `tiny` è il più rapido. `base`, `small` e `medium` richiedono progressivamente più risorse. La qualità dipende da lingua, rumore e chiarezza delle voci. La cattura di un browser può includere l’audio delle altre schede dello stesso processo.

Questo progetto deriva da [SubtitleForStream](https://github.com/tonythewizard/SubtitleForStream) ed è distribuito con licenza [GPL-3.0-only](LICENSE).
