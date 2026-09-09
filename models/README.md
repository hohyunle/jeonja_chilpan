# Offline OCR models

Place the two local PaddleOCR model directories here before packaging an offline
build:

```text
models/
├─ PP-OCRv5_mobile_det/
└─ korean_PP-OCRv5_mobile_rec/
```

Each directory must contain `inference.json` (or `inference.pdmodel`) and
`inference.pdiparams`. The model weights are intentionally kept out of the
source tree; use `tools/prepare_ocr_models.ps1` to copy an existing local
PaddleOCR cache into an ASCII-only runtime directory.
