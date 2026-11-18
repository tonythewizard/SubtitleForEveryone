# SubtitleForEveryone

Sottotitoli in tempo reale per persone sorde o ipoacusiche su Windows 11 x64. Puoi sottotitolare l’audio di Windows, per esempio un film riprodotto nel browser.

## Installer Windows

Scarica `SubtitleForEveryone-Setup-<versione>-x64.exe` dalla [repo delle release](https://github.com/tonythewizard/SubtitleForEveryone/releases). L’installer è per Windows 11 x64 e installa l’app per l’utente corrente, con collegamento nel menu Start e scorciatoia facoltativa sul desktop. Include Python, Qt, la cattura WASAPI, la traduzione locale e il backend whisper.cpp per Vulkan.

Su un PC senza GPU compatibile, usa **CPU**. Vulkan usa il driver grafico installato. Su una GPU NVIDIA, la prima selezione di **CUDA** nell’app installata scarica circa 1,3 GB di runtime ufficiali e li conserva nella cartella dell’utente. Anche i modelli vengono scaricati al primo utilizzo. L’installer non richiede Python, Visual Studio o Vulkan SDK sul PC di destinazione.

L’app installata confronta la propria versione con l’ultima release stabile di questa repo. Dopo conferma scarica il setup e ne verifica dimensione e SHA‑256 dai metadati GitHub. La repo deve essere pubblica per il controllo senza autenticazione. Le build da sorgente aprono la pagina della release.

## Installazione da sorgente

Installa Python 3.12 x64 con il launcher `py` e Visual Studio Build Tools con C++ desktop e Windows SDK. Da PowerShell esegui `.\setup_windows.ps1` per installare le dipendenze e compilare il componente audio, quindi avvia `run_windows.bat`.

## Uso

1. **Tutto l’audio delle app** cattura il parlato riprodotto dalle applicazioni Windows anche se usano uscite diverse. Per ascoltare una singola app, seleziona il processo o digita il nome, ad esempio `chrome.exe`.
2. Premi **Avvia**. Whisper rileva automaticamente la lingua parlata. In **Lingua dei sottotitoli** puoi mantenere l’originale o tradurre in italiano, inglese, spagnolo, francese o tedesco. La prima volta servono Internet e i modelli della coppia linguistica. Riconoscimento e traduzione avvengono in locale.
3. Trascina l’area del testo per spostare la finestra e usa l’angolo inferiore destro per ridimensionarla. Dal pannello principale puoi scegliere il font, il colore e la dimensione del testo, regolare l’opacità, impostare la priorità in primo piano e riattivare la barra del titolo.
4. Il **Monitor sottotitoli** mostra l’ultima frase in tempo reale. **Prova sottotitoli** visualizza un esempio anche con la trascrizione in pausa. Per i video a schermo intero, usa la modalità finestra senza bordi se il player in modalità esclusiva copre i sottotitoli.
5. La **X** del pannello principale lo nasconde nell’area di notifica. Dall’icona puoi riaprire il pannello, avviare o mettere in pausa la trascrizione, mostrare o nascondere i sottotitoli e uscire.
6. A trascrizione in pausa, regola il cursore **Velocità – Qualità**. Verso Velocità vedrai anteprime più brevi. Verso Qualità Whisper usa più contesto, aspetta la fine della frase e presenta i sottotitoli in ordine, dividendoli in più schermate quando serve. Se l’elaborazione resta indietro a lungo, la coda ha un limite.

In **Impostazioni** puoi seguire la lingua di Windows oppure scegliere italiano, inglese, spagnolo, francese o tedesco. Il cambio riavvia l’interfaccia e riprende una trascrizione attiva. Puoi abilitare l’avvio dell’app all’accesso a Windows e controllare le release pubbliche di GitHub manualmente o all’apertura dell’app.

## Accelerazione GPU da sorgente

- **CUDA** richiede una GPU NVIDIA con driver aggiornati. Dopo l’installazione esegui `.\setup_cuda.ps1` e scegli la tua GPU CUDA in **Elaborazione**.
- **Vulkan** richiede un driver Vulkan, `vulkaninfo` e un server whisper.cpp compilato con Vulkan. Esegui `.\setup_vulkan.ps1 -Model tiny -GpuIndex 1` per preparare e collaudare il server, sostituendo modello e indice con quelli scelti in **Elaborazione**. Per compilare il server lo script usa Visual Studio 2022 Build Tools con C++, CMake, Ninja e Vulkan SDK. Se disponi già di un server compilato, metti `whisper-server.exe` nella cartella `whisper-vulkan`.
- Lo stato mostra il backend in uso. In caso di errore GPU, l’app riprova con CPU INT8.

Il modello `tiny` è il più rapido. `base`, `small`, `medium` e `large-v3` richiedono progressivamente più risorse. Per provare `large-v3` con Vulkan usa `.\setup_vulkan.ps1 -Model large-v3 -GpuIndex 1` con l’indice della tua GPU. La qualità dipende da lingua, rumore e chiarezza delle voci. La cattura di un browser può includere l’audio delle altre schede dello stesso processo.

Quando avvii la trascrizione, l’app verifica i file del modello Whisper scelto confrontandoli con i checksum delle revisioni ufficiali. I modelli integri si avviano anche offline. I file mancanti o danneggiati vengono scaricati automaticamente. I nuovi file sono conservati in `%LOCALAPPDATA%\SubtitleForEveryone\models`, nelle sottocartelle `whisper` per CPU/CUDA e `vulkan` per Vulkan. L’app riusa anche i modelli ufficiali già presenti accanto a `whisper-server.exe`.

Questo progetto deriva da [SubtitleForStream](https://github.com/tonythewizard/SubtitleForStream) ed è distribuito con licenza [GPL-3.0-only](LICENSE).

## Build e release

Sul PC di build servono Visual Studio Build Tools con C++, CMake, Ninja, Vulkan SDK e Inno Setup 6. Installa `requirements-build.txt` nell’ambiente virtuale e imposta `VULKAN_SDK` sulla cartella dell’SDK. Esegui `.\build_windows.ps1` e poi `.\build_installer.ps1`. Il setup è generato in `installer`.

Il workflow **Windows installer** può generare un artefatto manualmente. Quando viene inviato un tag coerente con `VERSION`, compila su Windows, verifica l’installazione e pubblica il setup, il suo checksum e l’inventario delle dipendenze su GitHub Releases. Il setup corrente non è firmato con Authenticode. I componenti di terzi conservano le proprie licenze, comprese nella cartella `licenses` della build. Il binario Vulkan è compilato da [whisper.cpp v1.8.3](https://github.com/ggml-org/whisper.cpp/tree/v1.8.3).
