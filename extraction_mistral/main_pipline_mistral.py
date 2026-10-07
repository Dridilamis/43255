

import json
import os
from pathlib import Path

import fitz

try:
    from mistral_engine import (
        MistralSmall4ExactOCR,
    )
except ImportError:
    from mistral_engine import MistralSmall4ExactOCR


# ============================================================
# CHEMINS DU PROJET
# ============================================================

if os.name == "nt":
    BASE_DIR = (
        Path(os.environ.get("USERPROFILE", str(Path.home())))
        / "Desktop"
        / "TRACE"
        / "OCR vers LLM"
    )
else:
    BASE_DIR = Path.home() / "TRACE" / "OCR vers LLM"


INPUT_FOLDER = BASE_DIR / "suite pdfs annotés"

MISTRAL_OUT = BASE_DIR / "Mistral"

TXT_OUT = MISTRAL_OUT / "Sortie_Textes_Brut_MistralSmall49"

JSON_OUT = MISTRAL_OUT / "Sortie_JSON_TRACE_Sepsis_MistralSmall49"

TEMP_OUT = MISTRAL_OUT / "Temp_Images_MistralSmall4"


# ============================================================
# CONVERSION PDF → IMAGE
# ============================================================

def pdf_page_to_image(page, output_path, dpi=500):
    """
    Convertit une page PDF en image PNG.

    Le DPI élevé permet de conserver les petits caractères,
    les tableaux et les valeurs biologiques.
    """
    pix = page.get_pixmap(
        dpi=dpi,
        alpha=False
    )

    pix.save(str(output_path))


# ============================================================
# SAUVEGARDE DU FICHIER JSON
# ============================================================

def save_json(json_data, output_path):
    """
    Sauvegarde un dictionnaire Python dans un fichier JSON UTF-8.
    """
    with open(output_path, "w", encoding="utf-8") as json_file:
        json.dump(
            json_data,
            json_file,
            indent=4,
            ensure_ascii=False
        )


# ============================================================
# SAUVEGARDE DE LA TRANSCRIPTION BRUTE
# ============================================================

def save_raw_text(
    pdf_name,
    model_id,
    pages_resultats,
    pages_failed,
    output_path
):
    """
    Sauvegarde les transcriptions brutes page par page.
    """
    with open(output_path, "w", encoding="utf-8") as txt_file:

        txt_file.write(f"SOURCE : {pdf_name}\n")
        txt_file.write(f"MODELE : {model_id}\n")
        txt_file.write("TYPE : TRANSCRIPTION VISUELLE BRUTE MOT À MOT\n")
        txt_file.write("=" * 80)
        txt_file.write("\n\n")

        for page_result in pages_resultats:
            page_number = page_result.get("page", "inconnue")
            texte_brut = page_result.get("texte_brut", "")

            txt_file.write(f"--- PAGE {page_number} ---\n")
            txt_file.write(texte_brut.strip())
            txt_file.write("\n\n")

        if pages_failed:
            txt_file.write("\n")
            txt_file.write("=" * 80)
            txt_file.write("\nPAGES EN ÉCHEC\n")
            txt_file.write("=" * 80)
            txt_file.write("\n\n")

            for failed in pages_failed:
                txt_file.write(
                    f"Page {failed.get('page', 'inconnue')} : "
                    f"{failed.get('raison', 'raison inconnue')}\n"
                )


# ============================================================
# TRAITEMENT D'UN PDF
# ============================================================

def process_pdf(engine, pdf_path, pdf_index, total_pdfs):
    """
    Traite toutes les pages d'un document PDF :

    1. conversion de la page en image ;
    2. transcription visuelle par Mistral Small 4 ;
    3. extraction des entités ;
    4. extraction et validation des relations ;
    5. fusion au niveau du document ;
    6. sauvegarde JSON et TXT.
    """

    pdf_name = pdf_path.name
    base_name = pdf_path.stem

    print(
        f"\n[🔄 {pdf_index}/{total_pdfs}] "
        f"Traitement : {pdf_name}"
    )

    pages_resultats = []
    pages_failed = []

    document = None
    nb_pages = 0

    try:
        document = fitz.open(str(pdf_path))
        nb_pages = len(document)

        print(f"📄 Nombre de pages : {nb_pages}")

        for page_index in range(nb_pages):

            page_number = page_index + 1

            temp_image = (
                TEMP_OUT
                / f"{base_name}_page_{page_number}.png"
            )

            try:
                # ------------------------------------------------
                # 1. Conversion de la page PDF en image
                # ------------------------------------------------

                page = document.load_page(page_index)

                pdf_page_to_image(
                    page=page,
                    output_path=temp_image,
                    dpi=500
                )

                # ------------------------------------------------
                # 2. Lecture visuelle directe de la page
                # ------------------------------------------------

                ocr_result = engine.transcribe_page(
                    image_path=str(temp_image),
                    page_number=page_number
                )

                statut_ocr = ocr_result.get(
                    "statut",
                    "statut_inconnu"
                )

                texte_brut = ocr_result.get(
                    "texte_brut",
                    ""
                )

                # ------------------------------------------------
                # Contrôle de la transcription
                # ------------------------------------------------

                if (
                    statut_ocr != "ok"
                    or not isinstance(texte_brut, str)
                    or not texte_brut.strip()
                    or texte_brut.strip() == "[?]"
                ):
                    pages_failed.append({
                        "page": page_number,
                        "statut_ocr": statut_ocr,
                        "raison": (
                            "Transcription visuelle vide, "
                            "illisible ou en erreur"
                        ),
                        "texte_brut": texte_brut
                    })

                    print(
                        f"   Page {page_number}/{nb_pages} | "
                        f"Lecture visuelle=échec | ignorée"
                    )

                    continue

                # ------------------------------------------------
                # 3. Extraction ontologique TRACE-Sepsis
                # ------------------------------------------------

                ontology_result = engine.extract_ontology(
                    texte_brut=texte_brut,
                    page_number=page_number
                )

                if not isinstance(ontology_result, dict):
                    raise TypeError(
                        "extract_ontology() doit retourner un dictionnaire."
                    )

                entities = ontology_result.get(
                    "entities",
                    []
                )

                relations = ontology_result.get(
                    "relations",
                    []
                )

                if not isinstance(entities, list):
                    entities = []

                if not isinstance(relations, list):
                    relations = []

                if hasattr(engine, "prepare_entities_for_matching"):
                    entities = engine.prepare_entities_for_matching(
                        entities,
                        texte_brut
                    )

                sepsis_assessment = ontology_result.get(
                    "sepsis_assessment",
                    {}
                )

                quality_control = ontology_result.get(
                    "quality_control",
                    {}
                )

                # ------------------------------------------------
                # 4. Structure finale de la page
                # ------------------------------------------------

                page_data = {
                    "page": page_number,

                    "texte_brut": texte_brut,

                    "entities": entities,

                    "relations": relations,

                    "sepsis_assessment": sepsis_assessment,

                    "quality_control": quality_control,

                    "statut_ocr": statut_ocr,

                    "statut_ontologie": ontology_result.get(
                        "statut",
                        "inconnu"
                    ),

                    "statut_entites": ontology_result.get(
                        "statut_entites",
                        "inconnu"
                    ),

                    "statut_relations": ontology_result.get(
                        "statut_relations",
                        "inconnu"
                    )
                }

                pages_resultats.append(page_data)

                print(
                    f"   Page {page_number}/{nb_pages} | "
                    f"Lecture={page_data['statut_ocr']} | "
                    f"Entités={len(entities)} | "
                    f"Relations={len(relations)} | "
                    f"Statut relations="
                    f"{page_data['statut_relations']}"
                )

            except KeyboardInterrupt:
                print(
                    "\n⛔ Traitement interrompu manuellement."
                )
                raise

            except Exception as page_error:
                pages_failed.append({
                    "page": page_number,
                    "statut_ocr": "erreur_page",
                    "raison": str(page_error),
                    "texte_brut": ""
                })

                print(
                    f"❌ Erreur page {page_number} : "
                    f"{page_error}"
                )

            finally:
                # Suppression systématique de l'image temporaire
                try:
                    if temp_image.exists():
                        temp_image.unlink()

                except OSError as cleanup_error:
                    print(
                        f"⚠️ Impossible de supprimer "
                        f"{temp_image.name} : {cleanup_error}"
                    )

        # ========================================================
        # 5. FUSION DES RÉSULTATS AU NIVEAU DU DOCUMENT
        # ========================================================

        if not hasattr(engine, "merge_pages"):
            raise AttributeError(
                "Le moteur chargé ne contient pas merge_pages(). "
                "Utilise le moteur V6.5 FULL."
            )

        global_entities, global_relations = engine.merge_pages(
            pages_resultats
        )

        if hasattr(engine, "prepare_entities_for_matching"):
            global_entities = engine.prepare_entities_for_matching(
                global_entities
            )

        if hasattr(engine, "build_global_sepsis_assessment"):
            global_sepsis_assessment = (
                engine.build_global_sepsis_assessment(
                    pages_resultats
                )
            )
        else:
            global_sepsis_assessment = {}

        # ========================================================
        # 6. STRUCTURE JSON FINALE
        # ========================================================

        json_data = {
            "source_file": pdf_name,

            #"modele": engine.model_id,

            "type_extraction": (
                "lecture_visuelle_directe_plus_"
                "schema_trace_sepsis_detaille"
            ),

            "schema": {
                "name": "schema_trace_sepsis_fr",
                "version": getattr(engine, "schema_version", "1.6"),
                "description": (
                    "Extraction clinique structurée selon "
                    f"le schéma TRACE-Sepsis v{getattr(engine, 'schema_version', '1.6')}."
                ),

                "entity_types": sorted(
                    list(getattr(engine, "categories_autorisees", []))
                ),

                "relation_types": sorted(
                    list(getattr(engine, "relations_autorisees", []))
                )
            },

            "document_summary": {
                "total_pages_pdf": nb_pages,

                "pages_traitees": len(
                    pages_resultats
                ),

                "pages_failed": len(
                    pages_failed
                ),

                "total_entities": len(
                    global_entities
                ),

                "total_relations": len(
                    global_relations
                )
            },

            "global_entities": global_entities,

            "global_relations": global_relations,

            "global_sepsis_assessment": (
                global_sepsis_assessment
            ),

            "pages": pages_resultats,

            "pages_failed": pages_failed
        }

        # ========================================================
        # 7. NOMS DES FICHIERS DE SORTIE
        # ========================================================

        json_file = (
            JSON_OUT
            / f"{base_name}_trace_sepsis_V{getattr(engine, 'schema_version', '1.6')}.json"
        )

        txt_file = (
            TXT_OUT
            / f"{base_name}_brut.txt"
        )

        # ========================================================
        # 8. SAUVEGARDE
        # ========================================================

        save_json(
            json_data=json_data,
            output_path=json_file
        )

        save_raw_text(
            pdf_name=pdf_name,
            model_id=engine.model_id,
            pages_resultats=pages_resultats,
            pages_failed=pages_failed,
            output_path=txt_file
        )

        print(f"💾 JSON créé : {json_file}")
        print(f"💾 TXT créé : {txt_file}")

        print(
            f"📊 Résumé : "
            f"{len(pages_resultats)}/{nb_pages} pages traitées | "
            f"{len(global_entities)} entités | "
            f"{len(global_relations)} relations | "
            f"{len(pages_failed)} pages en échec"
        )

    except KeyboardInterrupt:
        raise

    except Exception as pdf_error:
        print(
            f"❌ Échec sur le document {pdf_name} : "
            f"{pdf_error}"
        )

    finally:
        if document is not None:
            document.close()


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():
    print(
        "🚀 Pipeline Mistral Small 4 : "
        "TRACE-Sepsis V6.5 SELECTIVE PRECISION FULL"
    )

    # ------------------------------------------------------------
    # Vérification du dossier d'entrée
    # ------------------------------------------------------------

    if not INPUT_FOLDER.exists():
        print(
            f"❌ Dossier PDF introuvable : "
            f"{INPUT_FOLDER}"
        )
        return

    # ------------------------------------------------------------
    # Création des dossiers de sortie
    # ------------------------------------------------------------

    TXT_OUT.mkdir(
        parents=True,
        exist_ok=True
    )

    JSON_OUT.mkdir(
        parents=True,
        exist_ok=True
    )

    TEMP_OUT.mkdir(
        parents=True,
        exist_ok=True
    )

    print(f"📂 PDF  : {INPUT_FOLDER}")
    print(f"📂 JSON : {JSON_OUT}")
    print(f"📂 TXT  : {TXT_OUT}")
    print(f"📂 TEMP : {TEMP_OUT}")

    # ------------------------------------------------------------
    # Initialisation de l'engine Mistral Small 4
    # ------------------------------------------------------------

    try:
        engine = MistralSmall4ExactOCR()

        print(
            f"✅ Engine chargé : "
            f"{getattr(engine, 'schema_version', 'version_inconnue')}"
        )
        print(
            f"✅ Modèle : "
            f"{getattr(engine, 'model_id', 'modele_inconnu')}"
        )

    except Exception as engine_error:
        print(
            f"❌ Impossible d'initialiser "
            f"MistralSmall4ExactOCR : {engine_error}"
        )
        return

    # ------------------------------------------------------------
    # Vérification de la clé API
    # ------------------------------------------------------------

    if not getattr(engine, "api_key", ""):
        print("❌ Clé API Mistral absente.")

        if os.name == "nt":
            print(
                '✅ PowerShell : '
                '$env:MISTRAL_API_KEY="ta_cle"'
            )
            print(
                '✅ Permanente : '
                'setx MISTRAL_API_KEY "ta_cle"'
            )

        else:
            print(
                "✅ Linux : "
                "export MISTRAL_API_KEY='ta_cle'"
            )

        return

    # ------------------------------------------------------------
    # Recherche des fichiers PDF
    # ------------------------------------------------------------

    pdf_files = sorted(
        [
            file
            for file in INPUT_FOLDER.iterdir()
            if file.is_file()
            and file.suffix.lower() == ".pdf"
        ],
        key=lambda path: path.name.lower()
    )

    if not pdf_files:
        print(
            f"❌ Aucun PDF trouvé dans : "
            f"{INPUT_FOLDER}"
        )
        return

    print(
        f"📚 {len(pdf_files)} PDF détecté(s)."
    )

    # ------------------------------------------------------------
    # Traitement de tous les PDF
    # ------------------------------------------------------------

    try:
        for pdf_index, pdf_path in enumerate(
            pdf_files,
            start=1
        ):
            process_pdf(
                engine=engine,
                pdf_path=pdf_path,
                pdf_index=pdf_index,
                total_pdfs=len(pdf_files)
            )

    except KeyboardInterrupt:
        print(
            "\n⛔ Pipeline interrompu par l'utilisateur."
        )
        return

    print("\n🏁 Pipeline Mistral Small 4 terminé.")


# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    main()
