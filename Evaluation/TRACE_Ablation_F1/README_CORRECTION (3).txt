CORRECTION DIRECTE V2

Corrections :
1. UTF-8 forcé pour éviter UnicodeEncodeError cp1252 sous PowerShell.
2. Les sous-processus Python sont lancés avec -X utf8.
3. Les matchers eux-mêmes reconfigurent stdout/stderr en UTF-8.
4. Si le dossier baseline historique est absent, les métriques baseline VALIDÉES sont utilisées comme ligne de référence :
   Entités relaxed : P=74.46%, R=68.10%, F1=71.14%, Macro F1=71.84%
   Relations relaxed : P=74.51%, R=63.62%, F1=68.64%, Macro F1=68.31%
5. Les algorithmes/seuils de matching ne sont pas modifiés.

Lancer :
python run_ablation_f1_TRACE.py
