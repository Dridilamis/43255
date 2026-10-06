Pattern C final corrigé
Ordre: detector -> validator -> generic_corrector -> post_validator.
Entrée: ../PatternB/PatternB2/corrected
Sorties locales: detection, validation, corrected, post_validation.

Correction importante:
Le validator n'autorise REPLACE_ENTITY_WITH_RELATION que si l'entité réifiée est
structurellement isolée. Cela rend la décision du validator cohérente avec les
règles de sécurité du correcteur. Les cas déjà reliés deviennent AMBIGUOUS/NONE
au lieu d'être annoncés comme correction future puis rejetés par le correcteur.
Le correcteur affiche séparément opérations autorisées et opérations appliquées.
