# SubtitleForEveryone

Sottotitoli in tempo reale per persone sorde o ipoacusiche su Windows 11 x64. Puoi leggere una conversazione catturata dal microfono o l’audio di un’applicazione, per esempio un video riprodotto nel browser.

## Installazione da sorgente

Installa Python 3.12 x64 con il launcher `py`. Da PowerShell, nella cartella del progetto, esegui `.\setup_windows.ps1`, quindi avvia `run_windows.bat`.

## Uso

1. Scegli il microfono o l’applicazione che riproduce l’audio. Se il processo non compare, aggiorna l’elenco o scrivi il suo nome, ad esempio `chrome.exe`.
2. Premi **Avvia**. Whisper riconosce la lingua parlata e produce sottotitoli nella stessa lingua. Il primo caricamento richiede Internet per scaricare il modello. Il riconoscimento successivo avviene localmente.
3. Trascina la barra della finestra dei sottotitoli per spostarla e usa l’angolo inferiore destro per ridimensionarla. Puoi regolare opacità dello sfondo, dimensione del testo e priorità in primo piano dal pannello principale.
4. **Prova sottotitoli** mostra un esempio senza catturare l’audio. Per i video a schermo intero, usa la modalità finestra senza bordi se il player in modalità esclusiva copre i sottotitoli.

Il modello `tiny` è il più rapido. `base`, `small` e `medium` richiedono progressivamente più risorse. La qualità dipende da lingua, rumore e chiarezza delle voci. La cattura di un browser può includere l’audio delle altre schede dello stesso processo.

Questo progetto deriva da [SubtitleForStream](https://github.com/tonythewizard/SubtitleForStream) ed è distribuito con licenza [GPL-3.0-only](LICENSE).
