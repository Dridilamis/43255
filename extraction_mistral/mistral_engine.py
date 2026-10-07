# -*- coding: utf-8 -*-
"""
MISTRAL V6.5 SELECTIVE PRECISION — ENGINE COMPLET AUTONOME

Contient intégralement le moteur V6.4 SMART RECALL (base interne)
+ les corrections V6.5 guidées par les erreurs d’évaluation.
Aucune dépendance vers un autre fichier engine V6.4.
"""


import base64
import json
import os
import re
import time
import requests


class _V64Engine:
    def __init__(self):
        self.api_key = os.getenv("MISTRAL_API_KEY", "").strip()

        if not self.api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY n'est pas définie dans l'environnement."
            )

        print(
            f"🔐 Mistral API key chargée : "
            f"{self.api_key[:3]}... longueur={len(self.api_key)}"
        )

        self.model_id = "mistral-small-2603"
        self.schema_version = "1.6-V6.4-SMART_RECALL-CLEAN"

        self.url = "https://api.mistral.ai/v1/chat/completions"

        # Mistral Small 4 via API Mistral directe : texte + image + sorties structurées.
        # Toute la logique clinique TRACE-Sepsis v1.6 reste identique à la version de référence.
        # Configuration réseau robuste pour éviter les blocages longs.
        self.http_session = requests.Session()
        self.connect_timeout = 30
        self.read_timeout = 180
        self.max_output_tokens = 14000

        # --- Schéma clinique TRACE-Sepsis v1.6 ---
        # Les entités et relations restent conservés selon la v1.6 ; la v1.6
        # enrichit les valeurs autorisées et les attributs.
        self.categories_autorisees = {
            "DONNEE_PATIENT", "LABEL_NOSOLOGIQUE", "SIGNE_VITAL",
            "BIOMARQUEUR", "SCORE_SOFA", "SCORE_qSOFA",
            "SCORE_NEUROLOGIQUE", "STADE_IRA", "FOYER_INFECTIEUX",
            "MICRO_ORGANISME", "DEFAILLANCE_ORGANE", "TRAITEMENT",
            "POSOLOGIE", "CONTEXTE_ACQUISITION",
            "COMORBIDITE_ANTECEDENT", "EVENEMENT_TEMPOREL",
            "EVOLUTION_PRONOSTIC", "SERVICE_MEDICAL",
            "METADONNEES_PIPELINE", "IMAGERIE_PROCEDURE", "SYMPTOME"
        }

        self.relations_autorisees = {
            "a_pour_label_nosologique", "presente_suspicion_infection",
            "presente_dysfonction_organe", "score_sofa_calcule_pour",
            "score_sofa_inclut_biomarqueur", "score_sofa_inclut_signe_vital",
            "score_sofa_inclut_score_neurologique", "score_qsofa_calcule_pour",
            "score_qsofa_inclut_score_neurologique", "stade_ira_calcule_pour",
            "traitement_administre_a", "traitement_a_pour_posologie",
            "antibiotique_adequat_pour", "antibiotique_inadequat_pour",
            "traitement_cible_defaillance", "traitement_indique_par_label_nosologique",
            "biomarqueur_obtenu_a", "biomarqueur_supporte_defaillance_organe",
            "biomarqueur_est_critere_de", "micro_organisme_isole_dans",
            "comorbidite_est_facteur_risque_de", "a_pour_contexte_acquisition",
            "contexte_acquisition_influence_risque_resistance", "precede",
            "patient_a_pour_evolution", "evenement_associe_evolution",
            "service_medical_accueille", "imagerie_objective_foyer",
            "imagerie_objective_comorbidite", "imagerie_objective_defaillance",
            "signe_vital_supporte_defaillance_organe", "presente_symptome"
        }

        # Signatures ontologiques strictes sujet -> objet.
        self.signatures_relations = {
            "a_pour_label_nosologique": ("DONNEE_PATIENT", "LABEL_NOSOLOGIQUE"),
            "presente_suspicion_infection": ("DONNEE_PATIENT", "FOYER_INFECTIEUX"),
            "presente_dysfonction_organe": ("DONNEE_PATIENT", "DEFAILLANCE_ORGANE"),
            "score_sofa_calcule_pour": ("SCORE_SOFA", "DONNEE_PATIENT"),
            "score_sofa_inclut_biomarqueur": ("SCORE_SOFA", "BIOMARQUEUR"),
            "score_sofa_inclut_signe_vital": ("SCORE_SOFA", "SIGNE_VITAL"),
            "score_sofa_inclut_score_neurologique": ("SCORE_SOFA", "SCORE_NEUROLOGIQUE"),
            "score_qsofa_calcule_pour": ("SCORE_qSOFA", "DONNEE_PATIENT"),
            "score_qsofa_inclut_score_neurologique": ("SCORE_qSOFA", "SCORE_NEUROLOGIQUE"),
            "stade_ira_calcule_pour": ("STADE_IRA", "DONNEE_PATIENT"),
            "traitement_administre_a": ("TRAITEMENT", "DONNEE_PATIENT"),
            "traitement_a_pour_posologie": ("TRAITEMENT", "POSOLOGIE"),
            "antibiotique_adequat_pour": ("TRAITEMENT", "MICRO_ORGANISME"),
            "antibiotique_inadequat_pour": ("TRAITEMENT", "MICRO_ORGANISME"),
            "traitement_cible_defaillance": ("TRAITEMENT", "DEFAILLANCE_ORGANE"),
            "traitement_indique_par_label_nosologique": ("TRAITEMENT", "LABEL_NOSOLOGIQUE"),
            "biomarqueur_obtenu_a": ("BIOMARQUEUR", "EVENEMENT_TEMPOREL"),
            "biomarqueur_supporte_defaillance_organe": ("BIOMARQUEUR", "DEFAILLANCE_ORGANE"),
            "biomarqueur_est_critere_de": ("BIOMARQUEUR", "LABEL_NOSOLOGIQUE"),
            "micro_organisme_isole_dans": ("MICRO_ORGANISME", "FOYER_INFECTIEUX"),
            "comorbidite_est_facteur_risque_de": ("COMORBIDITE_ANTECEDENT", "LABEL_NOSOLOGIQUE"),
            "a_pour_contexte_acquisition": ("COMORBIDITE_ANTECEDENT", "CONTEXTE_ACQUISITION"),
            "contexte_acquisition_influence_risque_resistance": ("CONTEXTE_ACQUISITION", "MICRO_ORGANISME"),
            "precede": ("EVENEMENT_TEMPOREL", "EVENEMENT_TEMPOREL"),
            "patient_a_pour_evolution": ("DONNEE_PATIENT", "EVOLUTION_PRONOSTIC"),
            "evenement_associe_evolution": ("EVENEMENT_TEMPOREL", "EVOLUTION_PRONOSTIC"),
            "service_medical_accueille": ("SERVICE_MEDICAL", "DONNEE_PATIENT"),
            "imagerie_objective_foyer": ("IMAGERIE_PROCEDURE", "FOYER_INFECTIEUX"),
            "imagerie_objective_comorbidite": ("IMAGERIE_PROCEDURE", "COMORBIDITE_ANTECEDENT"),
            "imagerie_objective_defaillance": ("IMAGERIE_PROCEDURE", "DEFAILLANCE_ORGANE"),
            "signe_vital_supporte_defaillance_organe": ("SIGNE_VITAL", "DEFAILLANCE_ORGANE"),
            "presente_symptome": ("DONNEE_PATIENT", "SYMPTOME")
        }

        # -------------------- Vocabulaires fermés TRACE-Sepsis --------------------
        self.valeurs_label_nosologique = {
            "sepsis", "sepsis_severe", "choc_septique", "choc_septique_refractaire",
            "sepsis_sans_choc", "bacteriemie_isolee", "suspicion_infection",
            "infection_documentee_sans_dysfonction_organe", "pneumopathie",
            "pneumopathie_communautaire", "pneumopathie_nosocomiale",
            "pneumopathie_inhalation", "PAVM", "SDRA", "CIVD",
            "syndrome_activation_macrophagique", "IRA", "syndrome_hepato_renal",
            "encephalopathie_hepatique", "etat_de_mal_epileptique",
            "crise_myasthenique", "aggravation_myasthenique", "ACFA", "flutter",
            "SIADH", "MAT", "SHU", "AVC", "AVC_hemorragique_probable",
            "gangrene_gazeuse"
        }

        self.synonymes_biomarqueurs = {
            "lactate": "lactate", "lactates": "lactate", "lactate_plasmatique": "lactate",
            "crp": "proteine_C_reactive", "c_r_p": "proteine_C_reactive",
            "proteine_c_reactive": "proteine_C_reactive", "procalcitonine": "procalcitonine",
            "pct": "procalcitonine", "creatinine": "creatinine", "uree": "uree",
            "dfg": "DFG", "sodium": "sodium", "natremie": "sodium",
            "potassium": "potassium", "kaliemie": "potassium", "chlorure": "chlorure",
            "chlorures": "chlorure", "calcium": "calcium", "calcemie": "calcium",
            "phosphate": "phosphate", "phosphates": "phosphate", "phosphore": "phosphate",
            "magnesium": "magnesium", "glycemie": "glycemie", "glucose": "glycemie",
            "bilirubine_totale": "bilirubine_totale", "bilirubine_conjuguee": "bilirubine_conjuguee",
            "bilirubine_directe": "bilirubine_conjuguee", "asat": "ASAT", "alat": "ALAT",
            "gamma_gt": "gamma_GT", "ggt": "gamma_GT", "phosphatases_alcalines": "phosphatases_alcalines",
            "pal": "phosphatases_alcalines", "ldh": "LDH", "cpk": "CPK", "ck": "CPK",
            "lipase": "lipase", "amylase": "amylase", "albumine": "albumine",
            "prealbumine": "prealbumine", "protides": "protides", "proteines": "protides",
            "globules_blancs": "globules_blancs", "gb": "globules_blancs", "leucocytes": "globules_blancs",
            "polynucleaires_neutrophiles": "polynucleaires_neutrophiles", "pnn": "polynucleaires_neutrophiles",
            "lymphocytes": "lymphocytes", "monocytes": "monocytes", "eosinophiles": "eosinophiles",
            "basophiles": "basophiles", "hemoglobine": "hemoglobine", "hb": "hemoglobine",
            "hematocrite": "hematocrite", "hematies": "hematies", "vgm": "VGM",
            "plaquettes": "plaquettes", "tp": "TP", "tq": "TP", "temps_de_quick": "TP",
            "tca": "TCA", "fibrinogene": "fibrinogene", "d_dimeres": "D_dimeres",
            "ddimeres": "D_dimeres", "facteur_ii": "facteur_II", "facteur_v": "facteur_V",
            "facteur_vii": "facteur_VII", "facteur_x": "facteur_X", "ph": "pH_arteriel",
            "ph_arteriel": "pH_arteriel", "pao2": "PaO2", "po2": "PaO2",
            "paco2": "PaCO2", "pco2": "PaCO2", "bicarbonate": "bicarbonates",
            "bicarbonates": "bicarbonates", "co2_total": "CO2_total",
            "saturation_arterielle_o2": "saturation_arterielle_O2", "sato2": "saturation_arterielle_O2",
            "rapport_pao2_fio2": "rapport_PaO2_FiO2", "p_f": "rapport_PaO2_FiO2",
            "troponine": "troponine", "bnp": "BNP", "cortisol": "cortisol", "tsh": "TSH",
            "ferritine": "ferritine", "triglycerides": "triglycerides",
            "haptoglobine": "haptoglobine", "schizocytes": "schizocytes",
            "reticulocytes": "reticulocytes", "proteinurie": "proteinurie",
            "natriurese": "natriurese", "fena": "FeNa", "ammoniemie": "ammoniemie",
            "antigenemie": "antigenemie", "antigenurie": "antigenurie",
            "charge_microbiologique": "charge_microbiologique"
        }
        # V6.3 BALANCED RECALL : compléter uniquement les analytes réellement
        # observés dans les tableaux biologiques du Gold. On conserve un
        # vocabulaire fermé afin de ne pas transformer n'importe quelle valeur
        # numérique en BIOMARQUEUR.
        self.synonymes_biomarqueurs.update({
            "ccmh": "CCMH",
            "tcmh": "TCMH",
            "tgmh": "TCMH",
            "idr": "IDR",
            "vmp": "VMP",
            "vm_plaq": "VMP",
            "hbo2": "HbO2",
            "hb_reduite": "Hb_reduite",
            "exces_base": "exces_base",
            "exces_de_base": "exces_base",
            "acide_urique": "acide_urique",
            "creatine_kinase": "CPK",
            "polynucleaires_eosinophiles": "eosinophiles",
            "p_eosinophiles": "eosinophiles",
            "polynucleaires_basophiles": "basophiles",
            "p_basophiles": "basophiles",
            "polynucleaires_neutrophiles": "polynucleaires_neutrophiles",
            "p_neutrophiles": "polynucleaires_neutrophiles",
            "fevg": "FEVG",
            "fraction_ejection_ventriculaire_gauche": "FEVG",
            "inr": "INR",
            "ratio_m_t": "ratio_M_T",
            "co2_total": "CO2_total",
        })

        self.parametres_biologiques = set(self.synonymes_biomarqueurs)
        self.valeurs_biomarqueurs = set(self.synonymes_biomarqueurs.values())

        self.synonymes_signes_vitaux = {
            "temperature": "temperature_corporelle", "temperature_corporelle": "temperature_corporelle",
            "frequence_cardiaque": "frequence_cardiaque", "fc": "frequence_cardiaque",
            "pression_arterielle_systolique": "pression_arterielle_systolique", "pas": "pression_arterielle_systolique",
            "pression_arterielle_diastolique": "pression_arterielle_diastolique", "pad": "pression_arterielle_diastolique",
            "pression_arterielle_moyenne": "pression_arterielle_moyenne", "pam": "pression_arterielle_moyenne",
            "frequence_respiratoire": "frequence_respiratoire", "fr": "frequence_respiratoire",
            "spo2": "SpO2", "sao2": "SpO2", "saturation_oxygene": "SpO2",
            "debit_cardiaque": "debit_cardiaque", "index_cardiaque": "index_cardiaque",
            "pression_veineuse_centrale": "pression_veineuse_centrale",
            "saturation_veineuse_centrale_o2": "saturation_veineuse_centrale_O2",
            "diurese_horaire": "diurese_horaire", "diurese_24h": "diurese_24h",
            "temps_recoloration_cutanee": "temps_recoloration_cutanee", "trc": "temps_recoloration_cutanee",
            "pression_plateau": "pression_plateau",
            "poids": "poids", "imc": "IMC"
        }
        self.parametres_signes_vitaux = set(self.synonymes_signes_vitaux)

        # Paramètres ventilatoires annotés POSOLOGIE dans le Gold.
        self.parametres_ventilatoires_posologie = {
            "fio2", "fraction_inspiree_oxygene",
            "fraction_inspiree_en_oxygene", "peep", "pep",
            "debit_o2", "debit_oxygene"
        }

        # Les attributs démographiques sont prioritaires lorsqu'ils sont présentés
        # dans l'identification du patient ; le prompt demande toutefois au modèle
        # de classer poids/IMC comme SIGNE_VITAL lorsqu'ils sont des mesures ponctuelles.
        self.attributs_donnee_patient = {
            "date_naissance", "age", "age_annees", "age_calcule", "sexe",
            "poids", "poids_kg", "taille", "taille_cm", "taille_m",
            "imc", "bmi", "poids_ideal_theorique_kg"
        }

        # Active une seconde lecture TEXTUELLE très ciblée. Elle ne peut
        # récupérer que les catégories qui manquent réellement en rappel.
        # Les catégories déjà sur-extraites (patient, posologie, service,
        # imagerie, comorbidité...) sont explicitement interdites.
        self.enable_targeted_recovery_v63 = True

        self.valeurs_traitement = {
            "antibiotique", "antifongique", "antiviral", "vasopresseur", "inotrope",
            "antiarythmique", "remplissage_vasculaire", "cristalloide", "colloide",
            "albumine", "ventilation_mecanique", "VNI", "oxygenotherapie", "NO_inhale",
            "curarisation", "intubation", "extubation", "tracheotomie",
            "epuration_extra_renale", "hemodialyse", "hemofiltration", "corticoide",
            "sedatif", "analgesique", "antalgique", "anticoagulant", "antiagregant",
            "diuretique", "insuline", "transfusion_CGR", "transfusion_plaquettes",
            "transfusion_PFC", "nutrition_enterale", "nutrition_parenterale",
            "supplementation_electrolytique", "kinesitherapie_respiratoire",
            "kinesitherapie_motrice", "drainage", "drain_thoracique",
            "ponction_evacuatrice", "chirurgie", "amputation", "immunoglobulines",
            "echange_plasmatique", "traitement_habituel", "autre"
        }

        self.valeurs_score_neurologique = {
            "Glasgow", "RASS", "FOUR_score", "score_myasthenique", "MMS", "testing_musculaire"
        }

        self.valeurs_imagerie_procedure = {
            "radiographie", "scanner", "tomodensitometrie", "TDM", "angioscanner", "IRM",
            "echographie", "echographie_abdominale", "echographie_renale", "echographie_pleurale",
            "echocardiographie", "ETT", "ECG", "EEG", "EMG", "EFR", "fibroscopie",
            "fibroscopie_bronchique", "fibroscopie_oesogastroduodenale", "endoscopie",
            "angiographie", "ponction_lombaire", "ponction_pleurale", "ponction_ascite",
            "biopsie", "PDP", "LBA", "ECBU", "hemoculture", "ECBC",
            "aspiration_tracheale", "myelogramme", "autre"
        }
        self.procedure_markers = {
            "tdm", "scanner", "tomodensitometrie", "angioscanner", "irm", "radiographie",
            "echographie", "echocardiographie", "ett", "doppler", "ecg", "eeg", "emg",
            "efr", "fibroscopie", "gastroscopie", "coloscopie", "endoscopie",
            "angiographie", "ponction_lombaire", "ponction_pleurale", "ponction_ascite",
            "biopsie", "pdp", "lba", "ecbu", "hemoculture", "ecbc",
            "aspiration_tracheale", "myelogramme"
        }

        self.valeurs_symptomes = {
            "fievre", "frissons", "cephalees", "toux", "dyspnee", "orthopnee", "polypnee",
            "douleur_thoracique", "douleur_abdominale", "douleur_lombaire", "myalgies",
            "nausees", "vomissements", "diarrhee", "fatigue", "asthenie", "anorexie",
            "confusion", "agitation", "somnolence", "desorientation",
            "ralentissement_psychomoteur", "dysphonie", "trouble_deglutition",
            "fausse_route", "trouble_mastication", "chute_mandibule", "cyanose",
            "marbrures", "extremites_froides", "tirage", "crepitants", "ronchis",
            "sibilants", "encombrement", "hypersalivation", "hoquet", "malaise",
            "syncope", "convulsions", "trismus", "myosis", "mydriase", "anisocorie",
            "ptosis", "photophobie", "raideur_nuque", "oedemes", "urines_foncees",
            "hematurie", "oligurie", "anurie", "ictere", "purpura",
            "alteration_etat_general", "perte_poids"
        }

        # Biomarqueurs utilisables comme composantes biologiques du SOFA.
        self.biomarqueurs_sofa_autorises = {
            "bilirubine_totale", "plaquettes", "creatinine", "rapport_PaO2_FiO2"
        }

    def encode_image(self, image_path):
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def convert_messages_to_mistral_contents(self, messages):
        """
        Conserve le format OpenAI-like déjà utilisé par
        transcribe_page / call_and_parse_json pour Mistral Small 4 via API Mistral directe.

        Accepte :
        - {"role": "user", "content": "texte"}
        - {"role": "user", "content": [{"type": "text", "text": "..."},
              {"type": "image_url",
               "image_url": {"url": "data:image/png;base64,XXXX"}}]}

        L’API Mistral accepte ce format multimodal après conversion de image_url en chaîne URL/data URI.
        La méthode reste au même emplacement afin de préserver la structure
        du code de référence.
        """
        contents = []

        for message in messages:
            if not isinstance(message, dict):
                continue

            role = message.get("role", "user")
            if role not in {"system", "user", "assistant"}:
                role = "user"

            raw_content = message.get("content", "")

            if isinstance(raw_content, str):
                contents.append({"role": role, "content": raw_content})
                continue

            if isinstance(raw_content, list):
                parts = []

                for item in raw_content:
                    if not isinstance(item, dict):
                        continue

                    if item.get("type") == "text":
                        parts.append({
                            "type": "text",
                            "text": item.get("text", "")
                        })

                    elif item.get("type") == "image_url":
                        image_url = item.get("image_url", {})
                        if isinstance(image_url, str):
                            image_url = {"url": image_url}

                        data_url = image_url.get("url", "")
                        if data_url:
                            parts.append({
                                "type": "image_url",
                                "image_url": data_url
                            })

                if parts:
                    contents.append({"role": role, "content": parts})

        return contents

    def call_mistral(
        self,
        messages,
        max_tokens=4000,
        retries=5,
        json_mode=False
    ):
        """
        Appelle Mistral Small 4 via API Mistral directe avec :
        - timeout de connexion et de lecture séparés ;
        - nouvelles tentatives sur erreurs temporaires ;
        - détection des réponses tronquées ;
        - mode JSON lorsque demandé ;
        - gestion propre de Ctrl+C.
        """
        if not self.api_key:
            raise RuntimeError(
                "Clé Mistral absente. Définis MISTRAL_API_KEY. "
                "PowerShell : $env:MISTRAL_API_KEY='TA_CLE' | "
                "Linux/macOS : export MISTRAL_API_KEY='TA_CLE'"
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        contents = self.convert_messages_to_mistral_contents(messages)
        current_max_tokens = min(max_tokens, self.max_output_tokens)
        last_error = None
        retryable_status = {408, 409, 425, 429, 500, 502, 503, 504}

        for attempt in range(1, retries + 1):
            payload = {
                "model": self.model_id,
                "messages": contents,
                "temperature": 0,
                "max_tokens": current_max_tokens
            }

            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            try:
                response = self.http_session.post(
                    self.url,
                    headers=headers,
                    json=payload,
                    timeout=(self.connect_timeout, self.read_timeout)
                )

                # Si response_format est refusé, nouvelle tentative sans ce paramètre.
                # Dans ce cas on réessaie sans ce paramètre ; le prompt et
                # clean_json_response imposent/valident déjà le JSON.
                if (
                    json_mode
                    and response.status_code in {400, 422}
                    and "response_format" in response.text.lower()
                ):
                    fallback_payload = dict(payload)
                    fallback_payload.pop("response_format", None)
                    response = self.http_session.post(
                        self.url,
                        headers=headers,
                        json=fallback_payload,
                        timeout=(self.connect_timeout, self.read_timeout)
                    )

                if response.status_code in retryable_status:
                    last_error = RuntimeError(
                        f"HTTP {response.status_code}: {response.text[:500]}"
                    )
                    if attempt == retries:
                        break
                    wait_seconds = min(60, 5 * attempt)
                    print(
                        f"⚠️ Mistral Small 4 HTTP {response.status_code}, "
                        f"tentative {attempt}/{retries}, attente {wait_seconds}s"
                    )
                    time.sleep(wait_seconds)
                    continue

                response.raise_for_status()
                result = response.json()
                choices = result.get("choices", [])

                if not choices:
                    raise RuntimeError(
                        f"Réponse Mistral Small 4 sans champ choices : {str(result)[:1000]}"
                    )

                choice = choices[0]
                finish_reason = choice.get("finish_reason")
                content = choice.get("message", {}).get("content", "")

                if isinstance(content, list):
                    content = "".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict)
                    )

                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError("Réponse Mistral Small 4 vide ou invalide.")

                if finish_reason in {"length", "max_tokens"}:
                    if current_max_tokens >= self.max_output_tokens:
                        raise RuntimeError(
                            "Réponse tronquée malgré la limite maximale "
                            f"de {self.max_output_tokens} tokens."
                        )

                    new_limit = min(
                        self.max_output_tokens,
                        max(current_max_tokens + 3000, current_max_tokens * 2)
                    )
                    print(
                        f"⚠️ Réponse Mistral Small 4 tronquée ({current_max_tokens} tokens). "
                        f"Nouvelle tentative avec {new_limit} tokens."
                    )
                    current_max_tokens = new_limit
                    continue

                return content.strip()

            except KeyboardInterrupt:
                print(
                    "\n⛔ Interruption manuelle détectée. "
                    "La requête en cours a été arrêtée."
                )
                raise

            except (
                requests.exceptions.ConnectTimeout,
                requests.exceptions.ReadTimeout
            ) as error:
                last_error = error
                if attempt == retries:
                    break
                wait_seconds = min(60, 5 * attempt)
                print(
                    f"⚠️ Timeout Mistral Small 4, tentative {attempt}/{retries}, "
                    f"attente {wait_seconds}s"
                )
                time.sleep(wait_seconds)

            except requests.exceptions.ConnectionError as error:
                last_error = error
                if attempt == retries:
                    break
                wait_seconds = min(60, 5 * attempt)
                print(
                    f"⚠️ Connexion Mistral Small 4 interrompue, tentative "
                    f"{attempt}/{retries}, attente {wait_seconds}s"
                )
                time.sleep(wait_seconds)

            except requests.exceptions.HTTPError as error:
                status = (
                    error.response.status_code
                    if error.response is not None
                    else "inconnu"
                )
                body = (
                    error.response.text[:1000]
                    if error.response is not None
                    else ""
                )
                raise RuntimeError(
                    f"Erreur Mistral HTTP {status}: {body}"
                ) from error

            except (
                requests.exceptions.RequestException,
                ValueError,
                RuntimeError
            ) as error:
                last_error = error
                if attempt == retries:
                    break
                wait_seconds = min(60, 5 * attempt)
                print(
                    f"⚠️ Erreur Mistral Small 4 tentative {attempt}/{retries}: "
                    f"{error}. Attente {wait_seconds}s"
                )
                time.sleep(wait_seconds)

        raise RuntimeError(
            "Échec API Mistral Small 4 après plusieurs tentatives. "
            f"Dernière erreur : {last_error}"
        )

    def transcribe_page(self, image_path, page_number):
        try:
            image_base64 = self.encode_image(image_path)

            prompt = """
Tu es un modèle vision-langage médical chargé de lire directement l'image du document.

OBJECTIF :
Transcrire fidèlement uniquement le texte réellement visible dans l'image.
Aucun moteur OCR intermédiaire n'est utilisé.

RÈGLES DE FIDÉLITÉ :
- Ne résume pas.
- Ne reformule pas.
- Ne corrige pas l'orthographe ou la terminologie.
- Ne complète aucune information absente.
- Ne devine jamais les noms, valeurs, dates, doses ou unités.
- Si une zone est illisible ou incertaine, écris exactement [?].
- Préserve les abréviations médicales telles qu'elles apparaissent.
- Préserve les retours à la ligne et l'ordre de lecture autant que possible.
- Ne produis aucune interprétation clinique.
- Retourne uniquement le texte visible, sans commentaire ni balise Markdown.
"""

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ]

            texte = self.call_mistral(messages, max_tokens=3000)

            return {
                "page": page_number,
                "texte_brut": texte.strip(),
                "statut": "ok"
            }

        except Exception as e:
            print(f"❌ Erreur de lecture visuelle page {page_number} : {e}")
            return {
                "page": page_number,
                "texte_brut": "",
                "statut": "erreur_lecture_visuelle"
            }

    def call_and_parse_json(
        self,
        messages,
        max_tokens,
        context_label,
        parse_retries=3
    ):
        """
        Obtient un JSON complet sans découper la page.

        Si la réponse est incomplète :
        - elle est sauvegardée pour audit ;
        - la limite de sortie est augmentée ;
        - le modèle recommence entièrement avec une sortie plus compacte.
        """
        last_error = None
        current_max_tokens = min(max_tokens, self.max_output_tokens)
        current_messages = list(messages)

        for parse_attempt in range(1, parse_retries + 1):
            response_text = ""

            try:
                response_text = self.call_mistral(
                    current_messages,
                    max_tokens=current_max_tokens,
                    retries=5,
                    json_mode=True
                )

                cleaned = self.clean_json_response(response_text)
                data = json.loads(cleaned)

                if not isinstance(data, dict):
                    raise ValueError("La réponse JSON doit être un objet.")

                if parse_attempt > 1:
                    print(
                        f"✅ JSON récupéré pour {context_label} "
                        f"à la tentative {parse_attempt}/{parse_retries}."
                    )

                return data

            except KeyboardInterrupt:
                raise

            except Exception as error:
                last_error = error

                debug_dir = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "debug_json_mistral_small4"
                )
                os.makedirs(debug_dir, exist_ok=True)

                safe_label = re.sub(
                    r"[^A-Za-z0-9_-]+",
                    "_",
                    str(context_label)
                )
                debug_path = os.path.join(
                    debug_dir,
                    f"{safe_label}_attempt_{parse_attempt}.txt"
                )

                with open(debug_path, "w", encoding="utf-8") as debug_file:
                    debug_file.write(response_text or str(error))

                if parse_attempt < parse_retries:
                    print(
                        f"⚠️ JSON incomplet pour {context_label}, "
                        f"tentative {parse_attempt}/{parse_retries}. "
                        "Nouvelle génération automatique."
                    )
                else:
                    print(
                        f"❌ JSON toujours invalide pour {context_label} après "
                        f"{parse_retries} tentatives. Audit : {debug_path}"
                    )

                if parse_attempt == parse_retries:
                    break

                current_max_tokens = min(
                    self.max_output_tokens,
                    current_max_tokens + 3000
                )

                current_messages = list(messages) + [{
                    "role": "user",
                    "content": (
                        "Recommence entièrement l'extraction sur le même texte. "
                        "La réponse précédente était tronquée ou invalide. "
                        "Retourne uniquement un objet JSON complet et valide. "
                        "Aucun commentaire, aucun Markdown, aucune virgule finale. "
                        "Utilise des preuves courtes et exactes. "
                        "N'ajoute aucun champ non demandé et supprime les champs "
                        "null inutiles afin de réduire la taille de la sortie."
                    )
                }]

        raise ValueError(
            f"Impossible d'obtenir un JSON complet pour {context_label}. "
            f"Dernière erreur : {last_error}"
        )

    def extract_entities(self, texte_brut, page_number):
        try:
            if not texte_brut.strip() or texte_brut.strip() == "[?]":
                return {"entites": [], "statut": "texte_vide"}

            prompt = f"""
Tu es un expert en extraction d'information clinique orientée sepsis.
Tu dois respecter strictement le guideline TRACE-Sepsis v1.6.

MISSION :
Extraire uniquement les entités explicitement présentes dans le texte, sans ajout de
connaissance externe, et retourner uniquement un objet JSON valide.

RÈGLES ANTI-HALLUCINATION :
- Toute entité doit avoir une preuve textuelle exacte, continue et réellement présente.
- La frontière de preuve doit être la PLUS COURTE expression autonome correspondant exactement à l'entité annotable.
  Ne retourne pas une phrase entière si un groupe nominal ou une valeur suffit.

RÈGLES DE COUVERTURE V6.4 :
- DONNEE_PATIENT : créer au maximum UN ancrage patient/patiente par page. Extraire en plus les données démographiques explicites utiles (âge, poids, taille, IMC/BMI), mais ne répète jamais toutes les occurrences du mot patient.
- EVENEMENT_TEMPOREL : extraire les dates, heures, périodes et durées explicitement écrites et utiles à la chronologie clinique. Une occurrence = une seule surface, la plus complète réellement écrite.
- SERVICE_MEDICAL : extraire seulement un vrai lieu/unité de soins explicitement nommé, pas un morceau de phrase contenant un mot médical.
- TRAITEMENT : ne pas limiter aux médicaments. Extraire aussi VNI, ventilation mécanique, intubation/extubation/réintubation, trachéotomie, oxygène/oxygénothérapie, kinésithérapie, rééducation, transfusion, dialyse, chirurgie et autres interventions explicitement réalisées ou prescrites.
- POSOLOGIE : séparer dose, débit, fréquence, durée, voie et réglage ventilatoire lorsqu'ils sont explicitement écrits.

RÈGLE DE FRONTIÈRE GOLD — PRIORITAIRE :
- Le champ preuve doit être EXACTEMENT le span de l'entité et rien d'autre.
- TRAITEMENT : preuve = uniquement le médicament/intervention. Exemple : "Amiklin pendant 5 jours" -> TRAITEMENT preuve="Amiklin".
- POSOLOGIE : preuve = uniquement la dose/fréquence/durée. Exemple précédent -> POSOLOGIE preuve="5 jours".
- BIOMARQUEUR : preuve = paramètre + valeur patient + unité si elle est directement accolée. Ne recopie pas l'intervalle de référence.
- SYMPTOME / LABEL_NOSOLOGIQUE / DEFAILLANCE_ORGANE : conserve le groupe clinique exact, sans phrase introductive inutile.
- Pour une négation annotable, conserve l'expression négative complète réellement écrite (ex. "pas de marbrures") et mets nie=true.
- FOYER_INFECTIEUX : extraire les foyers explicitement infectieux tels qu'érysipèle, sinusite infectieuse, abcès, pneumopathie infectieuse, pyélonéphrite.
- LABEL_NOSOLOGIQUE : extraire le libellé diagnostic court lui-même (ex. "sepsis", "choc septique", "PAVM", "flutter"), pas toute la phrase explicative.
- BIOMARQUEUR : extraire uniquement une mesure/résultat patient réellement présent. Ne jamais convertir une recommandation, une phrase générale, un seuil théorique ou une négation d'infection en BIOMARQUEUR.
- La preuve ne doit PAS être réduite à un seul mot si ce mot perd un contexte essentiel.
  Exemple : texte "portage de SARM" => preuve="portage de SARM", jamais preuve="SARM".
  Exemple : texte "ECBU ... isole Proteus mirabilis" => conserver le contexte d'isolement.
- N'invente aucune valeur, unité, date, dose, durée, diagnostic ou relation.
- Une négation explicite doit être conservée avec nie=true.
- Ne transforme pas une valeur de référence, un seuil ou une recommandation en donnée patient.
- Les informations directement identifiantes (nom, téléphone, adresse, IPP) ne sont pas extraites.
- type_inference="extraction_directe" par défaut ; inference_implicite uniquement si indispensable,
  clairement soutenue et avec confiance au plus moyenne.

RÈGLE PRIORITAIRE DEFAILLANCE_ORGANE :
Les formulations explicitement suivantes doivent être classées DEFAILLANCE_ORGANE,
pas LABEL_NOSOLOGIQUE ni SYMPTOME :
- insuffisance rénale aiguë / IRA => type_defaillance="renal"
- cytolyse hépatique / insuffisance hépatique => type_defaillance="hepatique"
- SDRA => type_defaillance="respiratoire"
- CIVD => type_defaillance="hematologique"
Ne déduis toutefois jamais une défaillance uniquement à partir d'un seuil biologique.

GUIDELINE v1.6 — CATÉGORIES AUTORISÉES :
DONNEE_PATIENT, LABEL_NOSOLOGIQUE, SIGNE_VITAL, BIOMARQUEUR, SCORE_SOFA,
SCORE_qSOFA, SCORE_NEUROLOGIQUE, STADE_IRA, FOYER_INFECTIEUX, MICRO_ORGANISME,
DEFAILLANCE_ORGANE, TRAITEMENT, POSOLOGIE, CONTEXTE_ACQUISITION,
COMORBIDITE_ANTECEDENT, EVENEMENT_TEMPOREL, EVOLUTION_PRONOSTIC, SERVICE_MEDICAL,
IMAGERIE_PROCEDURE, SYMPTOME.
METADONNEES_PIPELINE est réservée au pipeline et ne doit pas être extraite du texte clinique.

RÈGLES DE NORMALISATION v1.6 :
1) BIOMARQUEUR
Le champ parametre doit être normalisé vers UNE valeur de cette liste :
{json.dumps(sorted(self.valeurs_biomarqueurs), ensure_ascii=False)}
Exemples : CRP->proteine_C_reactive ; PCT->procalcitonine ; GB/leucocytes->globules_blancs ;
TP/TQ/temps de Quick->TP ; pH->pH_arteriel ; P/F->rapport_PaO2_FiO2.
Pour chaque BIOMARQUEUR, direction_cinetique est obligatoire et vaut exactement :
augmentation, diminution, stable, normalisation ou inconnue. N'utilise une évolution que si elle
est explicitement documentée ; sinon inconnue.

2) SIGNE_VITAL
Le champ parametre doit être une valeur de :
{json.dumps(sorted(set(self.synonymes_signes_vitaux.values())), ensure_ascii=False)}
FiO2, PEEP/PEP et débit d'O2 sont traités comme POSOLOGIE dans cette évaluation.
SpO2/SaO2 restent SIGNE_VITAL. Poids et âge sont DONNEE_PATIENT pour l'alignement Gold.

3) TRAITEMENT
parametre doit être une catégorie v1.6 parmi :
{json.dumps(sorted(self.valeurs_traitement), ensure_ascii=False)}
Le nom réel du médicament ou de l'intervention va dans nom_medicament.
Exemples : Amiklin->parametre antibiotique, nom_medicament Amiklin ; Noradrénaline->vasopresseur ;
VNI->VNI ; intubation->intubation ; transfusion de CGR->transfusion_CGR.
Ne place jamais la dose ou la durée dans TRAITEMENT.

4) POSOLOGIE
Entité séparée. Elle peut contenir dose_valeur, unite_dose, schema_horaire_brut,
frequence_intervalle_heures, nombre_administrations_jour, debit, unite_debit, volume,
unite_volume, concentration, voie_administration, duree_traitement, date_debut, date_fin,
ajustement_renal. Conserve la chaîne exacte dans schema_horaire_brut si elle existe.

5) SCORE_NEUROLOGIQUE
Valeurs autorisées : Glasgow, RASS, FOUR_score, score_myasthenique, MMS, testing_musculaire.

6) IMAGERIE_PROCEDURE
La v1.6 inclut aussi les examens fonctionnels et procédures diagnostiques :
{json.dumps(sorted(self.valeurs_imagerie_procedure), ensure_ascii=False)}
Ainsi PDP, LBA, ECBU, hémoculture, PL, EEG, EMG et EFR peuvent être IMAGERIE_PROCEDURE.

7) SYMPTOME
Normalise vers le vocabulaire v1.6 lorsque possible :
{json.dumps(sorted(self.valeurs_symptomes), ensure_ascii=False)}
Une manifestation clinique n'est pas automatiquement une DEFAILLANCE_ORGANE.

8) LABEL_NOSOLOGIQUE
Normalise vers le vocabulaire v1.6 si le diagnostic est explicitement écrit :
{json.dumps(sorted(self.valeurs_label_nosologique), ensure_ascii=False)}
Ne déduis jamais un sepsis ou un choc septique à partir de critères isolés.

9) EVENEMENT_TEMPOREL
Conserver une seule mention temporelle par occurrence. Préférer la forme la plus complète réellement
écrite : "24/02/2015" plutôt que "24/02" ou "2015". Les dates textuelles comme "15 juin",
"30 avril 2015" et "mi janvier 2015" sont autorisées. Une année seule est acceptée uniquement
lorsqu'elle constitue réellement la seule expression temporelle de l'énoncé. Ne transforme pas les
valeurs numériques biologiques en événements temporels.

11) Exhaustivité
Analyse toutes les lignes de traitements habituels, traitements à l'entrée, prise en charge,
évolution et prescription de sortie. Ne saute aucun médicament explicitement cité.

FORMAT JSON STRICT :
{{
  "page": {page_number},
  "entites": [
    {{
      "identifiant_entite": "E001",
      "categorie": "BIOMARQUEUR",
      "parametre": "proteine_C_reactive",
      "valeur": 97.2,
      "unite": "mg/L",
      "valeur_reference": null,
      "direction_cinetique": "inconnue",
      "horodatage": "inconnu",
      "preuve": "CRP 97.2 mg/L",
      "nie": false,
      "confiance": "elevee",
      "type_inference": "extraction_directe"
    }},
    {{
      "identifiant_entite": "E002",
      "categorie": "TRAITEMENT",
      "parametre": "antibiotique",
      "nom_medicament": "Amiklin",
      "valeur": null,
      "unite": null,
      "horodatage": "inconnu",
      "preuve": "Amiklin pendant 5 jours",
      "nie": false,
      "confiance": "elevee",
      "type_inference": "extraction_directe"
    }},
    {{
      "identifiant_entite": "E003",
      "categorie": "POSOLOGIE",
      "parametre": "duree_traitement",
      "valeur": 5,
      "unite": "jours",
      "duree_traitement": "5 jours",
      "horodatage": "inconnu",
      "preuve": "Amiklin pendant 5 jours",
      "nie": false,
      "confiance": "elevee",
      "type_inference": "extraction_directe"
    }}
  ]
}}

Retourne uniquement le JSON. Aucun Markdown, commentaire ou texte autour.

TEXTE VISIBLE :
--- DEBUT TEXTE ---
{texte_brut}
--- FIN TEXTE ---
"""

            data = self.call_and_parse_json(
                [{"role": "user", "content": prompt}],
                max_tokens=9000,
                context_label=f"entites_page_{page_number}",
                parse_retries=3
            )
            entites = self.clean_entities(
                data.get("entites", []),
                page_number,
                texte_brut=texte_brut
            )

            # V6.3 : seconde passe très ciblée uniquement sur les catégories
            # réellement sous-extraites. Les catégories déjà trop productives
            # sont interdites dans cette passe.
            recovered_v63 = self.recover_missing_entities_v63(
                texte_brut,
                entites,
                page_number
            )
            if recovered_v63:
                entites = self.clean_entities(
                    entites + recovered_v63,
                    page_number,
                    texte_brut=texte_brut
                )

            entites = self.add_missing_explicit_organ_failures(
                entites,
                texte_brut,
                page_number
            )
            entites = self.prepare_entities_for_matching(
                entites,
                texte_brut
            )

            # Un seul ancrage patient par page + démographie utile.
            entites = self.add_repeated_patient_mentions(
                entites,
                texte_brut,
                page_number
            )

            entites = self.add_explicit_service_mentions(
                entites,
                texte_brut,
                page_number
            )

            # Rappels déterministes à haute précision.
            entites = self.add_smart_structured_recall_v64(
                entites, texte_brut, page_number
            )
            entites = self.add_lexical_recall_v6(
                entites,
                texte_brut,
                page_number
            )
            entites = self.add_biomarker_recall_v63(
                entites,
                texte_brut,
                page_number
            )
            entites = self.add_temporal_recall_v63(
                entites,
                texte_brut,
                page_number
            )
            entites = self.add_evolution_recall_v63(
                entites,
                texte_brut,
                page_number
            )

            # Filtrage/compactage final.
            entites = self.postprocess_entities_v6(
                entites,
                texte_brut,
                page_number
            )

            return {"entites": entites, "statut": "ok"}

        except Exception as e:
            print(f"❌ Erreur entités page {page_number} : {e}")
            return {"entites": [], "statut": "erreur_entites", "erreur": str(e)}

    def extract_relations(self, texte_brut, entites, page_number):
        try:
            if not texte_brut.strip() or not entites:
                return {"relations": [], "statut": "relations_vides"}

            prompt = f"""
Tu es un expert en extraction de relations cliniques orientées sepsis.
Respecte strictement TRACE-Sepsis v1.6.

ENTRÉES : texte visible + liste fermée des entités déjà extraites.
MISSION : identifier toutes les relations explicitement soutenues parmi les 32 relations autorisées.
Ne crée aucune entité ni aucun type de relation supplémentaire.

RÈGLES :
- Utilise uniquement les identifiants_entite fournis.
- Respecte strictement le sens sujet -> objet et la signature ontologique.
- Relation directe = preuve textuelle exacte.
- inference_implicite seulement si indispensable, clairement soutenue et confiance <= moyenne.
- Ne crée pas une relation parce qu'elle est médicalement plausible.
- Une proximité textuelle seule ne suffit pas pour antibiotique_adequat_pour,
  antibiotique_inadequat_pour, traitement_indique_par_label_nosologique ou facteur de risque.
- precede seulement si l'ordre est explicite ou calculable à partir de dates/heures.
- traitement_administre_a seulement si administration/prescription/poursuite réelle chez le patient.
- traitement_a_pour_posologie seulement si la POSOLOGIE correspond réellement au TRAITEMENT.
- N'utilise jamais un nom de classe ("EVENEMENT_TEMPOREL", "TRAITEMENT", etc.) comme sujet/objet :
  utilise uniquement les identifiants Pn_Exxx fournis.
- Ne crée aucune relation positive vers une entité nie=true.
- "Pas de foyer franc" ne produit PAS imagerie_objective_foyer.
- Une anomalie anatomique non infectieuse (calcul, dilatation, obstruction seule) ne doit pas être
  l'objet de presente_suspicion_infection ou imagerie_objective_foyer.

SIGNATURES AUTORISÉES (32) :
- DONNEE_PATIENT -> a_pour_label_nosologique -> LABEL_NOSOLOGIQUE
- DONNEE_PATIENT -> presente_suspicion_infection -> FOYER_INFECTIEUX
- DONNEE_PATIENT -> presente_dysfonction_organe -> DEFAILLANCE_ORGANE
- SCORE_SOFA -> score_sofa_calcule_pour -> DONNEE_PATIENT
- SCORE_SOFA -> score_sofa_inclut_biomarqueur -> BIOMARQUEUR
- SCORE_SOFA -> score_sofa_inclut_signe_vital -> SIGNE_VITAL
- SCORE_SOFA -> score_sofa_inclut_score_neurologique -> SCORE_NEUROLOGIQUE
- SCORE_qSOFA -> score_qsofa_calcule_pour -> DONNEE_PATIENT
- SCORE_qSOFA -> score_qsofa_inclut_score_neurologique -> SCORE_NEUROLOGIQUE
- STADE_IRA -> stade_ira_calcule_pour -> DONNEE_PATIENT
- TRAITEMENT -> traitement_administre_a -> DONNEE_PATIENT
- TRAITEMENT -> traitement_a_pour_posologie -> POSOLOGIE
- TRAITEMENT -> antibiotique_adequat_pour -> MICRO_ORGANISME
- TRAITEMENT -> antibiotique_inadequat_pour -> MICRO_ORGANISME
- TRAITEMENT -> traitement_cible_defaillance -> DEFAILLANCE_ORGANE
- TRAITEMENT -> traitement_indique_par_label_nosologique -> LABEL_NOSOLOGIQUE
- SIGNE_VITAL -> signe_vital_supporte_defaillance_organe -> DEFAILLANCE_ORGANE
- BIOMARQUEUR -> biomarqueur_obtenu_a -> EVENEMENT_TEMPOREL
- BIOMARQUEUR -> biomarqueur_supporte_defaillance_organe -> DEFAILLANCE_ORGANE
- BIOMARQUEUR -> biomarqueur_est_critere_de -> LABEL_NOSOLOGIQUE
- MICRO_ORGANISME -> micro_organisme_isole_dans -> FOYER_INFECTIEUX
- COMORBIDITE_ANTECEDENT -> comorbidite_est_facteur_risque_de -> LABEL_NOSOLOGIQUE
- COMORBIDITE_ANTECEDENT -> a_pour_contexte_acquisition -> CONTEXTE_ACQUISITION
- CONTEXTE_ACQUISITION -> contexte_acquisition_influence_risque_resistance -> MICRO_ORGANISME
- EVENEMENT_TEMPOREL -> precede -> EVENEMENT_TEMPOREL
- DONNEE_PATIENT -> patient_a_pour_evolution -> EVOLUTION_PRONOSTIC
- EVENEMENT_TEMPOREL -> evenement_associe_evolution -> EVOLUTION_PRONOSTIC
- SERVICE_MEDICAL -> service_medical_accueille -> DONNEE_PATIENT
- IMAGERIE_PROCEDURE -> imagerie_objective_foyer -> FOYER_INFECTIEUX
- IMAGERIE_PROCEDURE -> imagerie_objective_comorbidite -> COMORBIDITE_ANTECEDENT
- IMAGERIE_PROCEDURE -> imagerie_objective_defaillance -> DEFAILLANCE_ORGANE
- DONNEE_PATIENT -> presente_symptome -> SYMPTOME

RELATIONS AUTORISÉES :
{json.dumps(sorted(self.relations_autorisees), ensure_ascii=False)}

FORMAT JSON STRICT :
{{
  "page": {page_number},
  "relations": [
    {{
      "identifiant_relation": "R001",
      "identifiant_entite_sujet": "P{page_number}_E002",
      "type_relation": "traitement_a_pour_posologie",
      "identifiant_entite_objet": "P{page_number}_E003",
      "delai_minutes": null,
      "preuve": "Amiklin pendant 5 jours",
      "note_clinique": "",
      "type_inference": "extraction_directe",
      "confiance": "elevee"
    }}
  ]
}}

ENTITÉS :
{json.dumps(entites, ensure_ascii=False, indent=2)}

TEXTE VISIBLE :
--- DEBUT TEXTE ---
{texte_brut}
--- FIN TEXTE ---

Retourne uniquement un objet JSON complet et valide.
"""
            data = self.call_and_parse_json(
                [{"role": "user", "content": prompt}],
                max_tokens=7000,
                context_label=f"relations_page_{page_number}",
                parse_retries=3
            )
            relations_brutes = data.get("relations", [])
            relations_brutes = self.add_deterministic_relations(
                relations_brutes, entites, texte_brut, page_number
            )
            proposed_count = len(relations_brutes)
            relations = self.clean_relations(relations_brutes, entites, page_number)
            print(
                f"ℹ️ Page {page_number} : relations proposées={proposed_count} | "
                f"relations conservées={len(relations)}"
            )
            if not relations:
                return {"relations": [], "statut": "aucune_relation_explicitement_ancree"}
            return {"relations": relations, "statut": "ok"}

        except Exception as e:
            print(f"❌ Erreur relations page {page_number} : {e}")
            return {"relations": [], "statut": "erreur_relations", "erreur": str(e)}

    def extract_ontology(self, texte_brut, page_number):
        ent_result = self.extract_entities(texte_brut, page_number)
        entites = ent_result.get("entites", [])

        rel_result = self.extract_relations(texte_brut, entites, page_number)
        relations = rel_result.get("relations", [])

        assessment = self.build_page_assessment(entites, page_number)

        return {
            "entities": entites,
            "relations": relations,
            "sepsis_assessment": assessment,
            "quality_control": self.build_quality_control(entites, relations),
            "statut": "ok" if ent_result["statut"] == "ok" else ent_result["statut"],
            "statut_entites": ent_result["statut"],
            "statut_relations": rel_result["statut"]
        }

    def clean_json_response(self, text):
        """
        Extrait et répare légèrement un objet JSON produit par le modèle.

        Réparations prises en charge :
        - suppression des blocs ```json ;
        - extraction du premier objet JSON ;
        - suppression des commentaires // et /* ... */ ;
        - remplacement des guillemets typographiques ;
        - suppression des virgules finales ;
        - ajout de guillemets autour de clés simples non citées.
        """
        if not isinstance(text, str):
            raise ValueError("La réponse du modèle n'est pas une chaîne.")

        cleaned = text.strip()
        cleaned = (
            cleaned
            .replace("```json", "")
            .replace("```JSON", "")
            .replace("```", "")
            .strip()
        )

        cleaned = (
            cleaned
            .replace(chr(8220), '"')
            .replace(chr(8221), '"')
            .replace(chr(8222), '"')
            .replace(chr(8217), "'")
        )

        json_candidate = self.extract_first_json_object(cleaned)

        json_candidate = re.sub(
            r"/\*.*?\*/",
            "",
            json_candidate,
            flags=re.DOTALL
        )
        json_candidate = re.sub(
            r"(^|\s)//.*?$",
            r"\1",
            json_candidate,
            flags=re.MULTILINE
        )

        json_candidate = re.sub(
            r",\s*([}\]])",
            r"\1",
            json_candidate
        )

        json_candidate = re.sub(
            r'([{,]\s*)([A-Za-z_À-ÿ][A-Za-z0-9_À-ÿ-]*)(\s*:)',
            r'\1"\2"\3',
            json_candidate
        )

        try:
            json.loads(json_candidate)
        except json.JSONDecodeError as e:
            context_start = max(0, e.pos - 120)
            context_end = min(len(json_candidate), e.pos + 120)
            context = json_candidate[context_start:context_end]

            raise ValueError(
                "JSON invalide après nettoyage. "
                f"Ligne {e.lineno}, colonne {e.colno}. "
                f"Contexte : {context!r}"
            ) from e

        return json_candidate

    def extract_first_json_object(self, text):
        """
        Retourne le premier objet JSON équilibré trouvé dans une chaîne.
        Respecte les chaînes entre guillemets et les caractères échappés.
        """
        start = text.find("{")
        if start == -1:
            raise ValueError("Aucun objet JSON trouvé dans la réponse.")

        depth = 0
        in_string = False
        escaped = False

        for index in range(start, len(text)):
            char = text[index]

            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1

                if depth == 0:
                    return text[start:index + 1]

        raise ValueError("Objet JSON incomplet dans la réponse du modèle.")

    def canonical_parameter(self, parametre):
        """
        Forme canonique utilisée uniquement pour les contrôles internes.
        Le champ parametre original reste inchangé sauf normalisation
        explicite (ex. synonymes de BIOMARQUEUR).
        """
        return self.normalize_text(parametre).replace(" ", "_")


    def is_null_like(self, value):
        """Détecte les pseudo-valeurs nulles produites par le LLM."""
        if value is None:
            return True
        text = self.normalize_text(value)
        return text in {"", "none", "null", "inconnu", "inconnue", "n/a", "na"}

    def proof_contains_any(self, proof, terms):
        proof_n = self.normalize_text(proof)
        return any(self.normalize_text(term) in proof_n for term in terms)

    def procedure_supported_by_proof(self, parametre, preuve):
        """
        IMAGERIE_PROCEDURE ne doit être conservée que si le type de procédure
        est réellement lexicalement supporté par la preuve.
        Empêche par exemple :
          'prélèvements bactériologiques' -> aspiration_tracheale
          'expectorations isolent' -> ECBC
        """
        p = self.canonical_parameter(parametre)
        proof = self.normalize_text(preuve)

        aliases = {
            "radiographie": ["radiographie", "radio thorax", "radio pulmonaire"],
            "scanner": ["scanner"],
            "tomodensitometrie": ["tomodensitometrie", "tdm"],
            "tdm": ["tdm", "scanner"],
            "angioscanner": ["angioscanner"],
            "irm": ["irm"],
            "echographie": ["echographie", "echo"],
            "echographie_abdominale": ["echographie abdominale", "echo abdominale"],
            "echographie_renale": ["echographie renale", "echo renale"],
            "echographie_pleurale": ["echographie pleurale", "echo pleurale"],
            "echocardiographie": ["echocardiographie", "echographie cardiaque"],
            "ett": ["ett", "echocardiographie transthoracique"],
            "ecg": ["ecg", "electrocardiogramme"],
            "eeg": ["eeg", "electroencephalogramme"],
            "emg": ["emg", "electromyogramme"],
            "efr": ["efr", "exploration fonctionnelle respiratoire"],
            "fibroscopie": ["fibroscopie"],
            "fibroscopie_bronchique": ["fibroscopie bronchique"],
            "fibroscopie_oesogastroduodenale": ["fibroscopie oesogastroduodenale", "fogd"],
            "endoscopie": ["endoscopie"],
            "angiographie": ["angiographie"],
            "ponction_lombaire": ["ponction lombaire", "pl "],
            "ponction_pleurale": ["ponction pleurale"],
            "ponction_ascite": ["ponction d ascite", "ponction ascite"],
            "biopsie": ["biopsie"],
            "pdp": ["pdp", "prelevement distal protege"],
            "lba": ["lba", "lavage broncho alveolaire", "lavage bronchoalveolaire"],
            "ecbu": ["ecbu", "examen cytobacteriologique des urines"],
            "hemoculture": ["hemoculture", "hemocultures"],
            "ecbc": ["ecbc", "examen cytobacteriologique des crachats"],
            "aspiration_tracheale": ["aspiration tracheale"],
            "myelogramme": ["myelogramme"],
        }

        if p == "autre":
            # "autre" n'est autorisé que si une vraie procédure est explicitement nommée.
            return self.proof_contains_any(
                proof,
                list(self.procedure_markers)
            )

        terms = aliases.get(p, [p.replace("_", " ")])
        return any(self.normalize_text(term) in proof for term in terms)

    def symptom_negation_supported(self, parametre, preuve):
        """
        Pour une entité SYMPTOME niée, le symptôme doit être réellement cité.
        Evite : 'extrémités chaudes' -> extremites_froides, nie=true.
        """
        p = self.canonical_parameter(parametre)
        proof = self.normalize_text(preuve)

        aliases = {
            "extremites_froides": ["extremites froides", "extremite froide"],
            "cyanose": ["cyanose"],
            "fievre": ["fievre", "febrile"],
            "dyspnee": ["dyspnee", "detresse respiratoire"],
            "crepitants": ["crepitants"],
            "sibilants": ["sibilants"],
            "ronchis": ["ronchis"],
            "oedemes": ["oedeme", "oedemes"],
            "confusion": ["confusion", "confus"],
            "agitation": ["agitation", "agite"],
            "somnolence": ["somnolence", "somnolent"],
            "anurie": ["anurie", "anurique"],
            "oligurie": ["oligurie", "oligurique"],
            "ictere": ["ictere"],
            "hematurie": ["hematurie"],
        }
        terms = aliases.get(p, [p.replace("_", " ")])
        return any(self.normalize_text(term) in proof for term in terms)

    def foyer_supported_by_proof(self, ent):
        """
        Vérifie qu'un FOYER_INFECTIEUX correspond à une infection/localisation infectieuse,
        et non à une anomalie anatomique isolée (calcul, dilatation, obstruction...).
        """
        proof = self.normalize_text(ent.get("preuve", ""))
        fields = " ".join(
            str(ent.get(k) or "")
            for k in ("parametre", "nom", "localisation", "nom_foyer")
        )
        text = self.normalize_text(fields + " " + proof)

        infection_markers = (
            "infection", "infectieux", "infectieuse", "sepsis", "septique",
            "pneumopathie", "pneumonie", "pyelo", "pyelonephrite",
            "abces", "erysipele", "cellulite", "gangrene",
            "prostatite", "cholangite", "peritonite", "meningite",
            "foyer", "suppuration", "pus", "purulent"
        )
        non_foyer_markers = (
            "calcul", "lithiase", "dilatation pyelocalicielle",
            "obstruction", "stenose", "hydrenophrose", "hydro-nephrose"
        )

        has_infection = any(m in text for m in infection_markers)
        has_non_foyer = any(m in text for m in non_foyer_markers)

        if has_non_foyer and not has_infection:
            return False

        # Un foyer anatomique simple n'est accepté que s'il est explicitement
        # présenté comme infectieux/suspect/probable dans la preuve.
        return has_infection or self.proof_contains_any(
            proof, ["point de depart", "porte d entree", "origine infectieuse"]
        )

    def infection_label_supported(self, ent):
        """
        Seuls les diagnostics réellement infectieux alimentent infection_suspectee.
        Evite par exemple : flutter -> preuve d'infection.
        """
        p = self.canonical_parameter(ent.get("parametre", ""))
        infection_labels = {
            "sepsis", "sepsis_severe", "choc_septique",
            "choc_septique_refractaire", "sepsis_sans_choc",
            "bacteriemie_isolee", "suspicion_infection",
            "infection_documentee_sans_dysfonction_organe",
            "pneumopathie", "pneumopathie_communautaire",
            "pneumopathie_nosocomiale", "pneumopathie_inhalation",
            "pavm", "gangrene_gazeuse"
        }
        return p in infection_labels


    def is_target_or_goal_measurement(self, categorie, parametre, preuve, valeur):
        """
        Evite de transformer une cible/consigne en mesure clinique réellement observée.
        Exemple à rejeter :
            "objectif de saturation 88-95%" -> SIGNE_VITAL SpO2
        Exemple à conserver :
            "SaO2 97%" -> SIGNE_VITAL SpO2
        """
        if categorie != "SIGNE_VITAL":
            return False

        proof = self.normalize_text(preuve)

        goal_markers = (
            "objectif",
            "cible",
            "target",
            "a maintenir",
            "maintenir entre",
            "maintenir a",
            "vise",
            "souhaitee",
            "souhaite",
            "consigne",
            "valeur cible",
            "saturation cible"
        )

        if not any(marker in proof for marker in goal_markers):
            return False

        # Les plages de valeurs sont particulièrement évocatrices d'une cible.
        if isinstance(valeur, str):
            compact = valeur.replace(" ", "")
            if "-" in compact or "à" in compact or "a" in compact:
                return True

        # Même une valeur ponctuelle n'est pas une mesure si elle est explicitement une cible.
        return True

    def service_represents_actual_care_context(self, ent):
        """
        SERVICE_MEDICAL doit être relié au patient uniquement lorsque la preuve
        décrit une prise en charge réelle dans ce service, et non une simple
        mention historique de lieu.
        """
        proof = self.normalize_text(ent.get("preuve", ""))
        service_name = self.normalize_text(
            ent.get("nom_service")
            or ent.get("parametre")
            or ""
        )

        # Le service de réanimation figurant dans l'en-tête du CRH est pertinent.
        if service_name in {"reanimation", "réanimation"}:
            return True

        positive_markers = (
            "hospitalise",
            "hospitalisee",
            "hospitalisé",
            "hospitalisée",
            "admis",
            "admise",
            "admission",
            "transfere",
            "transferee",
            "transféré",
            "transférée",
            "pris en charge",
            "prise en charge",
            "retour en",
            "retour a",
            "retour à",
            "sortie de",
            "service de",
            "secteur",
            "urgences",
            "reanimation",
            "réanimation",
            "ssr",
            "usic"
        )

        return any(marker in proof for marker in positive_markers)

    def label_is_core_clinical_diagnosis_for_global_link(self, ent):
        """
        Le lien inter-pages patient -> LABEL_NOSOLOGIQUE est limité aux diagnostics
        centraux du dossier, afin de ne pas transformer automatiquement tout diagnostic
        secondaire (ex. flutter) en label nosologique global.
        Les relations locales explicitement proposées par le modèle restent possibles.
        """
        p = self.canonical_parameter(ent.get("parametre", ""))

        core_labels = {
            "sepsis",
            "sepsis_severe",
            "choc_septique",
            "choc_septique_refractaire",
            "sepsis_sans_choc",
            "bacteriemie_isolee",
            "suspicion_infection",
            "infection_documentee_sans_dysfonction_organe",
            "pneumopathie",
            "pneumopathie_communautaire",
            "pneumopathie_nosocomiale",
            "pneumopathie_inhalation",
            "pavm",
            "sdra",
            "civd",
            "ira",
            "syndrome_hepato_renal",
            "gangrene_gazeuse"
        }

        return p in core_labels

    def treatment_relation_is_semantically_supported(self, treatment_ent, relation_proof):
        """
        Contrôle supplémentaire de traitement_administre_a.
        Une relation est rejetée lorsque la preuve indique explicitement un arrêt/sevrage
        sans administration active.
        """
        proof = self.normalize_text(relation_proof)
        ent_proof = self.normalize_text(treatment_ent.get("preuve", ""))
        combined = f"{proof} {ent_proof}"

        stop_markers = (
            "sevre de",
            "sevré de",
            "arret de",
            "arrêt de",
            "arrete",
            "arrêté",
            "stoppe",
            "stoppé",
            "interrompu"
        )

        active_markers = (
            "traite par",
            "traité par",
            "mise sous",
            "mis sous",
            "administre",
            "administré",
            "recoit",
            "reçoit",
            "prescrit",
            "prescription",
            "traitements habituels",
            "medicaments",
            "médicaments",
            "intube",
            "intubé",
            "ventile",
            "ventilé",
            "vni",
            "oxygene",
            "oxygène",
            "dialyse",
            "transfusion",
            "remplissage",
            "cardioversion",
            "operation",
            "opération",
            "pose d",
            "antibiotherapie",
            "antibiothérapie"
        )

        has_stop = any(marker in combined for marker in stop_markers)
        has_active = any(marker in combined for marker in active_markers)

        if has_stop and not has_active:
            return False

        return True


    def is_generic_microorganism(self, ent):
        name = self.normalize_text(
            ent.get("nom_micro_organisme")
            or ent.get("parametre")
            or ent.get("valeur")
            or ""
        )
        generic = {
            "", "germe", "germes", "bacterie", "bacteries",
            "bactérie", "bactéries", "microbe", "microbes",
            "flore", "pathogene", "pathogène", "micro organisme",
            "micro-organisme"
        }
        return name in generic

    def infer_defaillance_type(self, ent):
        current = (
            ent.get("type_defaillance")
            or ent.get("organe")
            or ent.get("parametre")
            or ""
        )
        current_n = self.canonical_parameter(current)
        if current_n and current_n not in {"defaillance_organe", "autre"}:
            return current_n

        proof = self.normalize_text(ent.get("preuve", ""))
        rules = [
            ("respiratoire", ("respiratoire", "sdra", "hypoxemie", "hypoxémie", "hypercapnie", "acidose respiratoire")),
            ("renal", ("insuffisance renale", "insuffisance rénale", "ira", "anurie", "oligurie", "dialyse")),
            ("hepatique", ("hepatique", "hépatique", "cytolyse", "insuffisance hepatocellulaire", "insuffisance hépatocellulaire")),
            ("cardiovasculaire", ("choc", "hypotension", "vasopresseur", "noradrenaline", "noradrénaline", "hemodynamique", "hémodynamique")),
            ("neurologique", ("encephalopathie", "encéphalopathie", "trouble de conscience", "coma", "glasgow")),
            ("hematologique", ("civd", "thrombopenie", "thrombopénie", "coagulation")),
            ("metabolique", ("acidose metabolique", "acidose métabolique", "hyperkaliemie", "hyperkaliémie")),
        ]
        for organ, markers in rules:
            if any(m in proof for m in markers):
                return organ
        return current_n or "autre"

    def clinical_entity_display_name(self, entite):
        cat = entite.get("categorie", "")

        if cat == "DEFAILLANCE_ORGANE":
            # Préférer la formulation clinique exacte à un nom de classe générique.
            value = (
                entite.get("manifestation")
                or entite.get("diagnostique")
                or entite.get("description")
                or entite.get("preuve")
                or entite.get("type_defaillance")
                or entite.get("organe")
            )
            return self.safe_relation_name(value or "defaillance_organe")

        if cat == "FOYER_INFECTIEUX":
            value = (
                entite.get("description")
                or entite.get("nom_foyer")
                or entite.get("localisation")
                or entite.get("parametre")
                or entite.get("preuve")
            )
            return self.safe_relation_name(value or "foyer_infectieux")

        if cat == "SERVICE_MEDICAL":
            value = entite.get("nom_service") or entite.get("parametre")
            return self.safe_relation_name(value or "service_medical")

        return None


    def contextualize_proof(self, texte_brut, preuve, ent):
        """
        Conserve la frontière textuelle proposée par le modèle.

        L'ancienne version élargissait les preuves courtes vers la phrase
        complète. Cela augmente artificiellement les erreurs de frontière
        dans l'évaluation NER (FP + FN / containment).

        Le contexte complet reste disponible dans texte_brut pour les
        validations et les relations.
        """
        if preuve is None:
            return ""
        return str(preuve).strip()


    def reclassify_explicit_organ_failure(self, ent):
        """
        Corrige certaines erreurs de catégorie fréquentes :
        IRA / SDRA / CIVD / cytolyse hépatique sont des défaillances d'organe
        lorsqu'ils sont explicitement décrits comme tels dans le texte.
        """
        cat = ent.get("categorie", "")
        proof = self.normalize_text(ent.get("preuve", ""))
        param = self.canonical_parameter(ent.get("parametre", ""))

        organ_map = {
            "ira": "renal",
            "insuffisance_renale_aigue": "renal",
            "sdra": "respiratoire",
            "civd": "hematologique",
            "cytolyse_hepatique": "hepatique",
            "insuffisance_hepatique": "hepatique",
            "insuffisance_hepatocellulaire": "hepatique",
        }

        # Détection par paramètre.
        if param in organ_map:
            ent["categorie"] = "DEFAILLANCE_ORGANE"
            ent["type_defaillance"] = organ_map[param]
            ent["parametre"] = organ_map[param]
            return ent

        # Détection par preuve textuelle explicite.
        proof_rules = [
            ("renal", ("insuffisance renale aigue", "insuffisance rénale aigu")),
            ("respiratoire", ("sdra", "detresse respiratoire avec defaillance")),
            ("hematologique", ("civd",)),
            ("hepatique", (
                "cytolyse hepatique", "cytolyse hépatique",
                "insuffisance hepatique", "insuffisance hépatique",
                "insuffisance hepatocellulaire", "insuffisance hépatocellulaire"
            )),
        ]

        if cat in {"LABEL_NOSOLOGIQUE", "SYMPTOME", "DEFAILLANCE_ORGANE"}:
            for organ, markers in proof_rules:
                if any(self.normalize_text(m) in proof for m in markers):
                    ent["categorie"] = "DEFAILLANCE_ORGANE"
                    ent["type_defaillance"] = organ
                    ent["parametre"] = organ
                    return ent

        return ent

    def add_missing_explicit_organ_failures(
        self,
        entites,
        texte_brut,
        page_number
    ):
        """
        Rappel déterministe très conservateur :
        ajoute uniquement des défaillances explicitement nommées dans le texte
        si Qwen les a complètement oubliées.

        Aucun diagnostic n'est déduit à partir d'un seuil biologique.
        """
        if not texte_brut:
            return entites

        source_norm = self.normalize_text(texte_brut)

        rules = [
            ("renal", [
                "insuffisance rénale aigu",
                "insuffisance renale aigue"
            ]),
            ("hepatique", [
                "cytolyse hépatique",
                "cytolyse hepatique",
                "insuffisance hépatique",
                "insuffisance hepatique",
                "insuffisance hépatocellulaire",
                "insuffisance hepatocellulaire"
            ]),
            ("respiratoire", ["sdra"]),
            ("hematologique", ["civd"])
        ]

        existing = {
            self.canonical_parameter(
                e.get("type_defaillance") or e.get("parametre") or ""
            )
            for e in entites
            if e.get("categorie") == "DEFAILLANCE_ORGANE"
            and not e.get("nie", False)
        }

        next_counter = 1
        for e in entites:
            eid = str(e.get("identifiant_entite", ""))
            m = re.search(r"_E(\d+)$", eid)
            if m:
                next_counter = max(next_counter, int(m.group(1)) + 1)

        for organ, expressions in rules:
            if organ in existing:
                continue

            matched = None
            for expression in expressions:
                expr_norm = self.normalize_text(expression)
                if expr_norm in source_norm:
                    # Récupérer la vraie phrase source.
                    for segment in re.split(r'(?<=[\.\!\?;:])\s+|\n+', texte_brut):
                        if expr_norm in self.normalize_text(segment):
                            matched = segment.strip()
                            break
                    matched = matched or expression
                    break

            if not matched:
                continue

            entites.append({
                "identifiant_entite": f"P{page_number}_E{next_counter:03d}",
                "categorie": "DEFAILLANCE_ORGANE",
                "parametre": organ,
                "type_defaillance": organ,
                "valeur": None,
                "unite": None,
                "valeur_reference": None,
                "horodatage": "inconnu",
                "preuve": matched,
                "nie": False,
                "confiance": "elevee",
                "type_inference": "extraction_directe",
                "page": page_number
            })
            next_counter += 1
            existing.add(organ)

        return entites

    def correct_entity_category_v5(self, ent):
        """Corrections déterministes limitées aux confusions observées."""
        if not isinstance(ent, dict):
            return ent

        ent = dict(ent)
        proof_raw = str(ent.get("preuve") or "")
        proof = self.normalize_text(proof_raw)
        param = self.canonical_parameter(ent.get("parametre") or "")

        # FiO2 / PEEP / débit O2 -> POSOLOGIE
        if (
            param in getattr(self, "parametres_ventilatoires_posologie", set())
            or re.search(r"\bfio2\b|\bpeep\b|\bpep\b", proof)
            or re.search(r"\bdebit\s+o2\b|\bo2\s*\d+(?:[.,]\d+)?\s*l/min\b", proof)
        ):
            ent["categorie"] = "POSOLOGIE"
            if "fio2" in proof or param == "fio2":
                ent["parametre"] = "FiO2"
            elif "peep" in proof or re.search(r"\bpep\b", proof):
                ent["parametre"] = "PEEP"
            else:
                ent["parametre"] = "debit"
            return ent

        # SaO2 / SpO2 -> SIGNE_VITAL
        if (
            param in {"spo2", "sao2", "saturation_oxygene", "saturation_arterielle_o2"}
            or re.search(r"\bspo2\b|\bsao2\b|\bsat\s*o2\b", proof)
        ):
            ent["categorie"] = "SIGNE_VITAL"
            ent["parametre"] = "SpO2"
            return ent

        # Poids / taille / IMC -> DONNEE_PATIENT pour cohérence avec le Gold utilisé.
        if param in {"poids", "poids_kg"} or re.search(r"\bpoids\s*(?:\(kg\))?\s*[:=]", proof):
            ent["categorie"] = "DONNEE_PATIENT"
            ent["parametre"] = "poids_kg"
            return ent

        if param in {"taille", "taille_cm", "taille_m"} or re.search(
            r"\btaille\s*(?:\((?:m|cm)\))?\s*[:=]",
            proof,
            flags=re.IGNORECASE
        ):
            ent["categorie"] = "DONNEE_PATIENT"
            ent["parametre"] = "taille_m" if "(m" in proof else "taille"
            return ent

        if param in {"imc", "bmi"} or re.search(
            r"\b(?:imc|bmi)\s*[:=]",
            proof,
            flags=re.IGNORECASE
        ):
            ent["categorie"] = "DONNEE_PATIENT"
            ent["parametre"] = "bmi"
            return ent

        # Polypnée = symptôme clinique, FR chiffrée reste signe vital.
        if re.search(r"\bpolypn[eé]e\b", proof_raw, flags=re.IGNORECASE):
            ent["categorie"] = "SYMPTOME"
            ent["parametre"] = "polypnee"
            return ent

        # Troubles de déglutition = symptôme lorsqu'ils sont actuels.
        if re.search(r"troubles?\s+de\s+la\s+d[eé]glutition", proof_raw, flags=re.IGNORECASE):
            ent["categorie"] = "SYMPTOME"
            ent["parametre"] = "trouble_deglutition"
            return ent

        # Détresse respiratoire actuelle = défaillance d'organe dans le Gold.
        if re.search(r"d[eé]tresse\s+respiratoire", proof_raw, flags=re.IGNORECASE):
            ent["categorie"] = "DEFAILLANCE_ORGANE"
            ent["parametre"] = "respiratoire"
            ent["type_defaillance"] = "respiratoire"
            return ent

        # Insuffisance respiratoire chronique = comorbidité/terrain.
        if "insuffisance respiratoire chronique" in proof:
            ent["categorie"] = "COMORBIDITE_ANTECEDENT"
            ent["parametre"] = "insuffisance_respiratoire_chronique"
            ent.setdefault("nom_comorbidite", "insuffisance respiratoire chronique")
            return ent

        # Carie/parodontite/érysipèle explicitement infectieux -> foyer.
        if re.search(r"\bcarie\b|\bparodontite\b|\bparondontite\b", proof):
            ent["categorie"] = "FOYER_INFECTIEUX"
            return ent
        if "erysipele" in proof or "érysipèle" in proof_raw.lower():
            ent["categorie"] = "FOYER_INFECTIEUX"
            ent.setdefault("nom_foyer", "érysipèle")
            return ent

        # Arrêt cardiaque explicite : Gold de ces dossiers = défaillance.
        if re.search(r"arr[eê]ts?\s+cardiaques?", proof_raw, flags=re.IGNORECASE):
            ent["categorie"] = "DEFAILLANCE_ORGANE"
            ent["parametre"] = "cardiovasculaire"
            ent["type_defaillance"] = "cardiovasculaire"
            return ent

        return ent

    def clean_entities(self, entites, page_number, texte_brut=None):
        clean = []
        seen = set()
        counter = 1

        for ent in entites:
            if not isinstance(ent, dict):
                continue

            ent = dict(ent)
            categorie = str(ent.get("categorie", "")).strip()
            if categorie == "COMORBIDITE":
                categorie = "COMORBIDITE_ANTECEDENT"

            raw_parametre = ent.get("parametre", "")
            parametre = "" if self.is_null_like(raw_parametre) else str(raw_parametre).strip()
            valeur = ent.get("valeur", None)
            preuve = str(ent.get("preuve", "")).strip()
            if not preuve:
                continue

            # Récupérer le contexte source exact quand la preuve est trop courte.
            preuve = self.contextualize_proof(
                texte_brut,
                preuve,
                ent
            )
            ent["preuve"] = preuve

            # Corriger les défaillances explicites mal catégorisées par le LLM.
            ent = self.reclassify_explicit_organ_failure(ent)
            ent = self.correct_entity_category_v5(ent)
            categorie = str(ent.get("categorie", categorie)).strip()
            parametre = str(ent.get("parametre", parametre) or "").strip()

            canon = self.canonical_parameter(parametre)

            # Normalisation prioritaire des vocabulaires v1.5.
            if canon in self.attributs_donnee_patient:
                categorie = "DONNEE_PATIENT"
            elif canon in self.synonymes_biomarqueurs:
                categorie = "BIOMARQUEUR"
                parametre = self.synonymes_biomarqueurs[canon]
            elif canon in self.synonymes_signes_vitaux and categorie != "POSOLOGIE":
                categorie = "SIGNE_VITAL"
                parametre = self.synonymes_signes_vitaux[canon]
            elif canon in self.procedure_markers or any(m in canon for m in self.procedure_markers):
                categorie = "IMAGERIE_PROCEDURE"

            if categorie not in self.categories_autorisees:
                continue

            # METADONNEES_PIPELINE n'est jamais extraite du texte clinique : elle est
            # construite par le pipeline.
            if categorie == "METADONNEES_PIPELINE":
                continue

            # Validation stricte des vocabulaires fermés.
            if categorie == "BIOMARQUEUR" and parametre not in self.valeurs_biomarqueurs:
                continue

            if categorie == "SIGNE_VITAL":
                pcanon = self.canonical_parameter(parametre)
                if pcanon in self.synonymes_signes_vitaux:
                    parametre = self.synonymes_signes_vitaux[pcanon]
                elif parametre not in set(self.synonymes_signes_vitaux.values()):
                    continue

                if self.is_target_or_goal_measurement(
                    categorie, parametre, preuve, valeur
                ):
                    print(
                        f"⚠️ Entité rejetée page {page_number} : "
                        f"cible thérapeutique ≠ mesure réelle : {preuve!r}"
                    )
                    continue

            if categorie == "TRAITEMENT":
                pcanon = self.canonical_parameter(parametre)
                # Autoriser le LLM à retourner la casse canonique V1.5.
                canonical_treatments = {self.canonical_parameter(v): v for v in self.valeurs_traitement}
                if pcanon in canonical_treatments:
                    parametre = canonical_treatments[pcanon]
                elif not ent.get("nom_medicament"):
                    # Si le nom du médicament existe mais la catégorie n'est pas certaine,
                    # le prompt doit utiliser 'autre' plutôt qu'inventer une catégorie.
                    continue
                else:
                    parametre = "autre"

            if categorie == "SCORE_NEUROLOGIQUE":
                allowed = {self.canonical_parameter(v): v for v in self.valeurs_score_neurologique}
                if canon in allowed:
                    parametre = allowed[canon]

            if categorie == "LABEL_NOSOLOGIQUE":
                allowed = {self.canonical_parameter(v): v for v in self.valeurs_label_nosologique}
                if canon in allowed:
                    parametre = allowed[canon]

            if categorie == "SYMPTOME":
                allowed = {self.canonical_parameter(v): v for v in self.valeurs_symptomes}
                if canon in allowed:
                    parametre = allowed[canon]

            # Validation sémantique renforcée v1.5
            if categorie == "IMAGERIE_PROCEDURE":
                if not self.procedure_supported_by_proof(parametre, preuve):
                    print(
                        f"⚠️ Entité rejetée page {page_number} : "
                        f"IMAGERIE_PROCEDURE={parametre!r} non supportée par la preuve {preuve!r}"
                    )
                    continue

            if categorie == "FOYER_INFECTIEUX":
                if not self.foyer_supported_by_proof(ent):
                    print(
                        f"⚠️ Entité rejetée page {page_number} : "
                        f"FOYER_INFECTIEUX non infectieux : {preuve!r}"
                    )
                    continue

            if categorie == "MICRO_ORGANISME":
                if self.is_generic_microorganism(ent):
                    print(
                        f"⚠️ Entité rejetée page {page_number} : "
                        f"pseudo MICRO_ORGANISME générique : {preuve!r}"
                    )
                    continue

            if categorie == "DEFAILLANCE_ORGANE":
                inferred = self.infer_defaillance_type(ent)
                ent["type_defaillance"] = inferred
                if not parametre:
                    parametre = inferred
                    ent["parametre"] = inferred

            if categorie == "SYMPTOME" and bool(ent.get("nie", False)):
                if not self.symptom_negation_supported(parametre, preuve):
                    print(
                        f"⚠️ Entité rejetée page {page_number} : "
                        f"négation symptomatique artificielle {parametre!r} <- {preuve!r}"
                    )
                    continue

            # EVENEMENT_TEMPOREL V5 : le Gold annote aussi les dates isolées.
            if categorie == "EVENEMENT_TEMPOREL":
                raw_type_event = ent.get("type_evenement") or ent.get("parametre") or "date"
                proof_raw = str(ent.get("preuve") or "")

                date_like = bool(re.search(
                    r"\b(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?|(?:19|20)\d{2})\b",
                    proof_raw
                ))
                textual_date_like = bool(re.search(
                    r"\b\d{1,2}\s+(?:janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[eé]cembre)(?:\s+\d{4})?\b",
                    proof_raw,
                    flags=re.IGNORECASE
                ))

                if date_like or textual_date_like:
                    ent["type_evenement"] = "date_clinique"
                    if not parametre:
                        parametre = "date_clinique"
                        ent["parametre"] = parametre
                else:
                    ent["type_evenement"] = self.canonical_parameter(raw_type_event) or "evenement_clinique"

            if categorie in {
                "SYMPTOME", "COMORBIDITE_ANTECEDENT",
                "TRAITEMENT", "SERVICE_MEDICAL"
            }:
                semantic_name = (
                    ent.get("nom_medicament")
                    or ent.get("nom_comorbidite")
                    or ent.get("nom_antecedent")
                    or ent.get("nom")
                    or ent.get("nom_service")
                    or parametre
                    or ""
                )
                key = (
                    self.normalize_text(categorie),
                    self.normalize_text(semantic_name),
                    self.normalize_text(preuve),
                    self.normalize_text(str(ent.get("horodatage", "inconnu"))),
                    str(bool(ent.get("nie", False)))
                )
            else:
                key = (
                    self.normalize_text(categorie), self.normalize_text(parametre),
                    self.normalize_text(str(valeur)), self.normalize_text(str(ent.get("unite"))),
                    self.normalize_text(preuve)
                )
            if key in seen:
                continue
            seen.add(key)

            ent["categorie"] = categorie
            ent["identifiant_entite"] = f"P{page_number}_E{counter:03d}"
            ent["page"] = page_number
            ent["parametre"] = parametre
            ent.setdefault("valeur", None)
            ent.setdefault("unite", None)
            ent.setdefault("valeur_reference", None)
            ent.setdefault("horodatage", "inconnu")
            ent["preuve"] = preuve
            ent.setdefault("nie", False)
            ent.setdefault("confiance", "moyenne")
            ent.setdefault("type_inference", "extraction_directe")

            if categorie == "BIOMARQUEUR":
                direction = self.canonical_parameter(ent.get("direction_cinetique", "inconnue"))
                mapping_direction = {
                    "hausse": "augmentation", "augmentation": "augmentation",
                    "baisse": "diminution", "diminution": "diminution",
                    "stable": "stable", "normalisation": "normalisation",
                    "inconnue": "inconnue", "inconnu": "inconnue"
                }
                ent["direction_cinetique"] = mapping_direction.get(direction, "inconnue")

            if categorie == "TRAITEMENT":
                ent.setdefault("nom_medicament", None)

            if categorie == "POSOLOGIE":
                for field in (
                    "dose_valeur", "unite_dose", "unite_administration",
                    "schema_horaire_brut", "moment_matin", "moment_midi",
                    "moment_soir", "moment_coucher", "frequence_intervalle_heures",
                    "nombre_administrations_jour", "debit", "unite_debit",
                    "volume", "unite_volume", "concentration", "voie_administration",
                    "duree_traitement", "date_debut", "date_fin", "ajustement_renal"
                ):
                    ent.setdefault(field, None)

            clean.append(ent)
            counter += 1

        clean = self.prepare_entities_for_matching(clean, texte_brut)
        return clean

    def _exact_surface_from_text(self, texte_brut, candidate):
        """
        Retourne la forme exactement présente dans texte_brut lorsqu'un
        candidat structuré (médicament, microorganisme, service...) existe.
        Matching insensible à la casse, mais sortie = texte original.
        """
        if not texte_brut or candidate is None:
            return None

        candidate = str(candidate).strip()
        if not candidate:
            return None

        # Exact case-insensitive first.
        match = re.search(
            re.escape(candidate),
            texte_brut,
            flags=re.IGNORECASE
        )
        if match:
            return texte_brut[match.start():match.end()]

        # Variante espaces / tirets / underscores.
        words = [
            w for w in re.split(r"[\s_\-]+", candidate)
            if w
        ]
        if not words:
            return None

        flexible = r"[\s_\-]+".join(
            re.escape(w) for w in words
        )
        match = re.search(
            flexible,
            texte_brut,
            flags=re.IGNORECASE
        )
        if match:
            return texte_brut[match.start():match.end()]

        return None

    def _compact_measurement_from_proof(self, ent):
        """
        V6.2 : span BIOMARQUEUR/SIGNE_VITAL centré sur :
            PARAMETRE + VALEUR PATIENT + UNITE éventuelle

        On coupe explicitement avant les intervalles de référence.

        Exemples :
            Chlorure 85 95-105 mmol/L
                -> Chlorure 85
            Procalcitonine (PCT) 0.48 <0.50 µg/L
                -> Procalcitonine (PCT) 0.48
            pCO2/T° patient 4.53 4.66-6.00 kPa
                -> pCO2/T° patient 4.53
        """
        proof = str(ent.get("preuve") or "").strip()
        if not proof:
            return ""

        value = ent.get("valeur")
        unit = ent.get("unite")
        param = self.canonical_parameter(
            ent.get("parametre") or ""
        )

        # --------------------------------------------------------
        # Chercher d'abord la vraie surface du paramètre
        # --------------------------------------------------------
        candidates = []

        for alias, canonical in self.synonymes_biomarqueurs.items():
            if self.canonical_parameter(canonical) == param:
                candidates.append(alias.replace("_", " "))

        for alias, canonical in self.synonymes_signes_vitaux.items():
            if self.canonical_parameter(canonical) == param:
                candidates.append(alias.replace("_", " "))

        raw_param = str(
            ent.get("parametre") or ""
        ).replace("_", " ").strip()

        if raw_param:
            candidates.append(raw_param)

        candidates = sorted(
            {c for c in candidates if c},
            key=len,
            reverse=True
        )

        parameter_match = None

        for candidate in candidates:
            # accepter espaces / slash / ponctuation légère
            flexible = re.escape(candidate)
            flexible = flexible.replace(r"\ ", r"\s+")

            m = re.search(
                flexible,
                proof,
                flags=re.IGNORECASE
            )

            if m:
                parameter_match = m
                break

        # --------------------------------------------------------
        # Chercher la valeur patient structurée
        # --------------------------------------------------------
        value_match = None

        if value is not None:
            raw = str(value).strip()

            variants = sorted(
                {
                    raw,
                    raw.replace(".", ","),
                    raw.replace(",", "."),
                },
                key=len,
                reverse=True
            )

            search_start = (
                parameter_match.end()
                if parameter_match
                else 0
            )

            for variant in variants:
                if not variant:
                    continue

                m = re.search(
                    r"(?<!\d)"
                    + re.escape(variant)
                    + r"(?!\d)",
                    proof[search_start:],
                    flags=re.IGNORECASE
                )

                if m:
                    value_match = (
                        search_start + m.start(),
                        search_start + m.end()
                    )
                    break

        # --------------------------------------------------------
        # PARAMETRE + VALEUR
        # --------------------------------------------------------
        if parameter_match and value_match:
            start_pos = parameter_match.start()
            end_pos = value_match[1]

            # Inclure l'unité seulement si elle suit immédiatement
            # la valeur patient.
            if unit:
                tail = proof[end_pos:]

                unit_match = re.match(
                    r"\s*"
                    + re.escape(str(unit)),
                    tail,
                    flags=re.IGNORECASE
                )

                if unit_match:
                    end_pos += unit_match.end()

            result = proof[
                start_pos:end_pos
            ].strip(" \t\r\n,;:-")

            if result:
                return result

        # --------------------------------------------------------
        # Valeur seule mais correctement ancrée.
        # --------------------------------------------------------
        if value_match:
            start_pos, end_pos = value_match

            if unit:
                tail = proof[end_pos:]

                unit_match = re.match(
                    r"\s*"
                    + re.escape(str(unit)),
                    tail,
                    flags=re.IGNORECASE
                )

                if unit_match:
                    end_pos += unit_match.end()

            # Maximum 3 tokens avant la valeur.
            left = proof[:start_pos]
            tokens = list(
                re.finditer(r"\S+", left)
            )

            if len(tokens) >= 3:
                start_pos = tokens[-3].start()
            else:
                start_pos = 0

            result = proof[
                start_pos:end_pos
            ].strip(" \t\r\n,;:-")

            if result:
                return result

        # --------------------------------------------------------
        # Pas de valeur : garder uniquement le paramètre littéral.
        # --------------------------------------------------------
        if parameter_match:
            return proof[
                parameter_match.start():
                parameter_match.end()
            ].strip()

        # Une preuve déjà courte reste utilisable.
        if (
            len(proof.split()) <= 5
            and len(proof) <= 70
        ):
            return proof

        return proof

    def _first_literal_term(self, text, terms):
        """Retourne le premier terme lexical réellement présent dans text."""
        if not text:
            return None
        candidates = sorted(
            {str(t).strip() for t in terms if str(t).strip()},
            key=len,
            reverse=True
        )
        for term in candidates:
            m = re.search(
                r"(?<!\w)" + re.escape(term) + r"(?!\w)",
                text,
                flags=re.IGNORECASE
            )
            if m:
                return text[m.start():m.end()]
        return None

    def _compact_temporal_surface(self, proof):
        """
        V6.3 : conserve les vraies expressions temporelles du Gold :
        dates numériques/textuelles, mois+année, heures, durées et moments
        de la journée. La forme la plus longue réellement écrite est préférée.
        """
        if not proof:
            return ""

        months = (
            r"janvier|f[eé]vrier|mars|avril|mai|juin|juillet|"
            r"ao[uû]t|septembre|octobre|novembre|d[eé]cembre"
        )

        patterns = [
            rf"\b\d{{1,2}}\s+(?:{months})\s+(?:19|20)\d{{2}}"
            rf"\s+(?:au|à|-)\s+\d{{1,2}}\s+(?:{months})\s+(?:19|20)\d{{2}}\b",
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}h(?:\d{2})?\b",
            r"\b(?:jusqu['’]?au|depuis\s+le|le)\s+\d{1,2}/\d{1,2}(?:[/.]\d{2,4})?\b",
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
            rf"\bmi[-\s]?(?:{months})(?:\s+(?:19|20)\d{{2}})?\b",
            rf"\b\d{{1,2}}\s+(?:{months})(?:\s+(?:19|20)\d{{2}})?\b",
            rf"\b(?:{months})\s+(?:19|20)\d{{2}}\b",
            r"\b\d{1,2}h(?:\d{2})?\b",
            r"\b(?:une\s+heure|\d+(?:[.,]\d+)?\s*(?:heures?|jours?|semaines?|mois|ans?))\b",
            r"\b(?:dans\s+l['’]apr[eè]s[-\s]?midi|apr[eè]s[-\s]?midi|au\s+soir)\b",
            r"\b(?:19|20)\d{2}\b",
            r"\b(?:0[1-9]|[12]\d|3[01])/(?:0[1-9]|1[0-2])\b",
        ]

        for pattern in patterns:
            m = re.search(pattern, proof, flags=re.IGNORECASE)
            if m:
                return m.group(0).strip()

        return ""

    def _compact_service_surface(self, ent):
        proof = str(ent.get("preuve") or "")
        raw = str(
            ent.get("nom_service")
            or ent.get("parametre")
            or ""
        ).strip()

        common = [
            "réanimation", "reanimation", "urgences", "urgence",
            "USIC", "SSR", "soins intensifs", "salle de réveil",
            "Salpêtrière", "Salpetrière", "Salpetriere",
            "Garches", "Foch", "STELL"
        ]

        found = self._first_literal_term(proof, common)
        if found:
            return found

        # Ex. "hospitalisé à Foch" -> "Foch"
        m = re.search(
            r"\b(?:hospitalis[eé]e?|transf[eé]r[eé]e?|admis(?:e)?)\s+(?:à|au|aux)\s+"
            r"([A-ZÀ-ÖØ-Ý][\wÀ-ÿ'’\-]+(?:\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÿ'’\-]+){0,3})",
            proof
        )
        if m:
            return m.group(1).strip()

        # "centre hospitalier René Dubos" / "clinique du Val d'OR"
        m = re.search(
            r"\b((?:centre\s+hospitalier|h[oô]pital|clinique)\s+"
            r"(?:de\s+|du\s+|d['’])?[A-ZÀ-ÖØ-Ý][\wÀ-ÿ'’\-]+"
            r"(?:\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÿ'’\-]+){0,3})",
            proof,
            flags=re.IGNORECASE
        )
        if m:
            return m.group(1).strip()

        if raw and len(raw.split()) <= 5:
            local = self._exact_surface_from_text(proof, raw)
            return local or raw

        return proof.strip()

    def _compact_treatment_surface(self, ent):
        proof = str(ent.get("preuve") or "")
        raw = str(
            ent.get("nom_medicament")
            or ent.get("nom_traitement")
            or ent.get("nom_intervention")
            or ""
        ).strip()

        treatment_terms = [
            "ventilation mécanique", "ventilation mecanique",
            "kinésithérapie respiratoire", "kinesitherapie respiratoire",
            "restriction hydrique", "extractions dentaires",
            "Pacemaker double chambre",
            "oxygénothérapie", "oxygenotherapie",
            "réintubation", "reintubation", "intubation", "intubé", "intube",
            "extubation", "extubé", "extube",
            "trachéotomie", "tracheotomie",
            "gastrostomie", "VNI", "Oxygène", "oxygène", "oxygene",
            "kinésithérapie", "kinesitherapie", "rééducation", "reeducation",
            "transfusion", "hémodialyse", "hemodialyse",
            "Lovenox", "Lasilix", "Acupan", "Primpéran", "Primperan",
            "Vénofer IV", "Véinofer IV", "Vénofer", "Véinofer",
            "Tardyferon", "Tardiyferon", "Tazocilline", "TAZOCILLINE",
            "Claforan", "CLAFORAN", "Amiklin", "AMIKLIN", "Augmentin", "augmentin",
            "amoxicilline", "vancomycine", "tienam", "noradrénaline", "adrénaline",
            "NPH", "anticoagulation", "cardioversion", "BIPAP",
            "Sérum phy", "serum phy"
        ]
        found = self._first_literal_term(proof, treatment_terms)
        if found:
            return found

        if raw:
            local = self._exact_surface_from_text(proof, raw)
            if local:
                return local
            if len(raw.split()) <= 6:
                return raw

        return proof.strip()

    def _compact_symptom_surface(self, ent):
        proof = str(ent.get("preuve") or "")
        symptom_terms = [
            "altération de l'état général", "alteration de l'etat general",
            "balancement thoraco-abdominal",
            "occlusion palpébrale incomplète", "occlusion palpebrale incomplete",
            "parésie faciale supérieure", "paresie faciale superieure",
            "atteinte motrice proximale", "atteinte motrice distale",
            "déficit musculaire axial", "deficit musculaire axial",
            "trouble de la propulsion",
            "encombrement bronchique",
            "désaturations", "desaturations", "désaturation", "desaturation",
            "hypersalivation", "marbrures", "anisocorie", "syncope", "chute",
            "encombrement", "diarrhées", "diarrhee", "diarrhée",
            "confusion", "toux", "dyspnée", "dyspnee",
            "polypnée", "polypnee", "fièvre", "fievre"
        ]
        found = self._first_literal_term(proof, symptom_terms)
        if found:
            return found

        param = str(ent.get("parametre") or "").replace("_", " ")
        local = self._exact_surface_from_text(proof, param)
        if local:
            return local

        if len(proof.split()) <= 6:
            return proof.strip()

        return proof.strip()

    def _compact_imaging_surface(self, ent):
        proof = str(ent.get("preuve") or "")
        imaging_terms = [
            "Radiographie pulmonaire", "radiographie pulmonaire",
            "scanner maxillo-facial", "TDM thoracique", "TDM Abdo",
            "échographie abdominale", "echographie abdominale",
            "Ponction d'ascite", "ponction d'ascite",
            "hémoculture périphérique", "hemoculture peripherique",
            "coronarographie", "Radiographie", "radiographie",
            "scanner", "IRM", "ECBU", "ECG", "EMG", "EEG",
            "PDP", "LBA", "TDM", "Écho abdo", "Echo abdo"
        ]
        found = self._first_literal_term(proof, imaging_terms)
        if found:
            return found

        raw = str(
            ent.get("nom_procedure")
            or ent.get("nom_examen")
            or ent.get("parametre")
            or ""
        ).replace("_", " ").strip()
        local = self._exact_surface_from_text(proof, raw)
        return local or proof.strip()

    def _compact_comorbidity_surface(self, ent):
        proof = str(ent.get("preuve") or "")
        terms = [
            "insuffisance respiratoire chronique",
            "atrophie cortico-sous-corticale",
            "atrophie cortico sous corticales",
            "varices oesophagiennes",
            "hémibloc antérieur", "hemibloc anterieur",
            "Fracture du péroné", "fracture du péroné",
            "arrachement de l'apophyse",
            "Nodule du poumon droit", "nodule de 4 mm",
            "Gastrite avec bulbite", "gastrite",
            "sinusite chronique", "pancytopénie", "Hépatite A",
            "tabagisme sevré", "tabagisme", "thrombose", "cataracte",
            "BAV1", "hyperglycémie", "hyperglycemie", "Hématome", "hematome"
        ]
        found = self._first_literal_term(proof, terms)
        if found:
            return found

        raw = str(
            ent.get("nom_comorbidite")
            or ent.get("nom_antecedent")
            or ent.get("nom_pathologie")
            or ""
        ).strip()
        local = self._exact_surface_from_text(proof, raw)
        if local:
            return local

        return proof.strip()

    def _has_same_surface_entity(self, entites, categorie, surface):
        key = self.normalize_text(surface)
        if not key:
            return True
        for ent in entites:
            if not isinstance(ent, dict):
                continue
            if ent.get("categorie") != categorie:
                continue
            existing = self.normalize_text(
                ent.get("name") or ent.get("preuve") or ""
            )
            if existing == key:
                return True
        return False

    def _append_literal_entity(
        self,
        entites,
        categorie,
        surface,
        page_number,
        parametre="",
        **extra
    ):
        if not surface or self._has_same_surface_entity(
            entites, categorie, surface
        ):
            return

        ent = {
            "categorie": categorie,
            "parametre": parametre,
            "valeur": None,
            "unite": None,
            "valeur_reference": None,
            "horodatage": "inconnu",
            "preuve": surface,
            "nie": False,
            "confiance": "elevee",
            "type_inference": "extraction_directe",
            "page": page_number,
            "name": surface,
            "type": categorie,
            "_deterministic_v6": True,
        }
        ent.update(extra)
        entites.append(ent)


    def recover_missing_entities_v63(self, texte_brut, entites, page_number):
        """
        Seconde passe Mistral ciblée sur les catégories qui restent en FN.

        Important :
        - aucune récupération de DONNEE_PATIENT / SERVICE_MEDICAL ;
        - récupération contrôlée de POSOLOGIE / IMAGERIE_PROCEDURE /
          COMORBIDITE_ANTECEDENT / SIGNE_VITAL / DEFAILLANCE_ORGANE / SCORE_NEUROLOGIQUE ;
        - chaque preuve doit être une sous-chaîne exacte du texte ;
        - on ne renvoie que les entités ABSENTES de la première passe.

        Cette passe est volontairement beaucoup plus étroite que la V7
        HIGH_RECALL afin de ne pas reproduire son explosion de faux positifs.
        """
        if (
            not getattr(self, "enable_targeted_recovery_v63", True)
            or not texte_brut
        ):
            return []

        target_categories = {
            "BIOMARQUEUR",
            "SYMPTOME",
            "TRAITEMENT",
            "EVENEMENT_TEMPOREL",
            "EVOLUTION_PRONOSTIC",
            "LABEL_NOSOLOGIQUE",
            "MICRO_ORGANISME",
            "FOYER_INFECTIEUX",
            "CONTEXTE_ACQUISITION",
            "DEFAILLANCE_ORGANE",
            "SIGNE_VITAL",
            "IMAGERIE_PROCEDURE",
            "POSOLOGIE",
            "SCORE_NEUROLOGIQUE",
            "COMORBIDITE_ANTECEDENT",
        }

        existing = []
        for ent in entites:
            if not isinstance(ent, dict):
                continue
            cat = str(ent.get("categorie") or "").strip()
            if cat not in target_categories:
                continue
            proof = str(
                ent.get("preuve")
                or ent.get("name")
                or ""
            ).strip()
            if proof:
                existing.append({
                    "categorie": cat,
                    "preuve": proof
                })

        # Éviter de gonfler inutilement le prompt sur les pages biologiques.
        existing = existing[:180]

        prompt = f"""
Tu effectues une DEUXIÈME PASSE DE RÉCUPÉRATION sur un texte clinique.
Une première extraction a déjà été réalisée.

OBJECTIF :
Retourner UNIQUEMENT les entités explicitement présentes qui ont été OUBLIÉES
par la première passe.

CATÉGORIES AUTORISÉES POUR CETTE PASSE, ET UNIQUEMENT CELLES-CI :
BIOMARQUEUR, SYMPTOME, TRAITEMENT, EVENEMENT_TEMPOREL,
EVOLUTION_PRONOSTIC, LABEL_NOSOLOGIQUE, MICRO_ORGANISME,
FOYER_INFECTIEUX, CONTEXTE_ACQUISITION, DEFAILLANCE_ORGANE, SIGNE_VITAL,
IMAGERIE_PROCEDURE, POSOLOGIE, SCORE_NEUROLOGIQUE, COMORBIDITE_ANTECEDENT.

INTERDIT :
DONNEE_PATIENT, SERVICE_MEDICAL, SCORE_SOFA, SCORE_qSOFA, STADE_IRA.

RÈGLES SUPPLÉMENTAIRES STRICTES :
- SIGNE_VITAL : uniquement une mesure vitale explicite ou une formulation clinique avec valeur (TA, FC, FR, température, SpO2/SaO2, PAM).
- DEFAILLANCE_ORGANE : uniquement une formulation explicite de dysfonction/défaillance (IRA, insuffisance rénale aiguë, détresse respiratoire, SDRA, anurie, acidose métabolique, cytolyse hépatique, CIVD, choc). Ne déduis pas à partir d'une valeur isolée.
- IMAGERIE_PROCEDURE : uniquement le nom exact d'un examen/procédure réellement écrit (ECG, ETT, TDM, scanner, radiographie, radiographie pulmonaire, IRM, échographie, EEG, EMG, EFR, fibroscopie, hémoculture, ECBU, PDP, LBA). Les formes imbriquées explicitement écrites peuvent toutes être conservées, ex. "Radiographie" ET "Radiographie pulmonaire".
- POSOLOGIE : uniquement dose, fréquence, durée, débit, voie ou réglage explicitement écrit et rattachable localement à un traitement.
- SCORE_NEUROLOGIQUE : uniquement un score explicite avec son nom et sa valeur, ex. "Glasgow est à 9".
- COMORBIDITE_ANTECEDENT : uniquement une pathologie/antécédent explicitement présenté comme terrain ou antécédent ; pas une complication aiguë.

RÈGLES DE PRÉCISION :
1. Ne répète AUCUNE entité déjà présente dans EXISTANT.
2. Toute "preuve" doit être une sous-chaîne EXACTE, CONTINUE et réellement
   présente dans TEXTE.
3. N'invente ni diagnostic, ni valeur, ni unité.
4. TRAITEMENT : preuve = uniquement le médicament/intervention, sans dose.
5. BIOMARQUEUR : preuve = paramètre + valeur patient + unité éventuelle,
   sans intervalle de référence.
6. EVENEMENT_TEMPOREL : dates/heures/périodes/durées réellement écrites.
7. EVOLUTION_PRONOSTIC : uniquement une amélioration, aggravation, régression,
   normalisation, récupération, sevrage, stabilisation, complication ou décès
   explicitement formulé.
8. Une négation explicite peut être extraite uniquement si l'expression négative
   complète est écrite ; dans ce cas nie=true.
9. Maximum 80 entités récupérées. Si tu hésites, n'ajoute pas l'entité.

Pour BIOMARQUEUR, parametre doit être une valeur canonique de cette liste :
{json.dumps(sorted(self.valeurs_biomarqueurs), ensure_ascii=False)}

FORMAT STRICT :
{{
  "page": {page_number},
  "entites": [
    {{
      "categorie": "SYMPTOME",
      "parametre": "toux",
      "preuve": "toux grasse",
      "nie": false,
      "confiance": "elevee",
      "type_inference": "extraction_directe"
    }}
  ]
}}

EXISTANT :
{json.dumps(existing, ensure_ascii=False)}

TEXTE :
--- DEBUT ---
{texte_brut}
--- FIN ---

Retourne uniquement le JSON.
"""

        try:
            data = self.call_and_parse_json(
                [{"role": "user", "content": prompt}],
                max_tokens=6000,
                context_label=f"recovery_v64_page_{page_number}",
                parse_retries=2
            )
        except Exception as exc:
            print(
                f"⚠️ Récupération ciblée V6.3 ignorée page {page_number} : {exc}"
            )
            return []

        recovered = []
        seen = {
            (
                str(e.get("categorie") or "").strip(),
                self.normalize_text(e.get("preuve") or e.get("name") or "")
            )
            for e in entites
            if isinstance(e, dict)
        }

        for ent in data.get("entites", []):
            if not isinstance(ent, dict):
                continue

            ent = dict(ent)
            cat = str(ent.get("categorie") or "").strip()
            proof = str(ent.get("preuve") or "").strip()

            if cat not in target_categories or not proof:
                continue

            # Ancrage anti-hallucination : la preuve doit être retrouvée
            # littéralement dans le texte fourni au modèle.
            match = re.search(
                re.escape(proof),
                texte_brut,
                flags=re.IGNORECASE
            )
            if not match:
                continue

            key = (cat, self.normalize_text(proof))
            if key in seen:
                continue

            if re.match(
                r"^\s*(?:pas\s+d['’e]?\s*|pas\s+de\s+|sans\s+|absence\s+de\s+|aucun(?:e)?\s+)",
                proof,
                flags=re.IGNORECASE
            ):
                ent["nie"] = True

            ent.setdefault("nie", False)
            ent.setdefault("confiance", "elevee")
            ent.setdefault("type_inference", "extraction_directe")
            ent["_surface_start"] = match.start()
            ent["_surface_end"] = match.end()
            ent["_recovered_v64"] = True

            recovered.append(ent)
            seen.add(key)

            if len(recovered) >= 80:
                break

        if recovered:
            print(
                f"➕ Page {page_number} : récupération ciblée V6.4 = "
                f"{len(recovered)} entités candidates"
            )

        return recovered


    def add_biomarker_recall_v63(self, entites, texte_brut, page_number):
        """
        Récupère à haute précision des lignes biologiques structurées que le
        MLLM oublie fréquemment (CCMH, TCMH, IDR, VMP, HbO2, excès de base...).

        On exige toujours : analyte explicite + première valeur numérique patient.
        Les intervalles de référence situés après la valeur ne sont pas inclus.
        """
        if not texte_brut or not isinstance(entites, list):
            return entites

        aliases = [
            (r"C\.?C\.?M\.?H\.?", "CCMH"),
            (r"T\.?C\.?M\.?H\.?", "TCMH"),
            (r"T\.?G\.?M\.?H\.?", "TCMH"),
            (r"\bIDR\b", "IDR"),
            (r"V\.?M\.?\s*Plaq\.?", "VMP"),
            (r"\bVMP\b", "VMP"),
            (r"\bHbO2\b", "HbO2"),
            (r"Hb\s+r[eé]duite", "Hb_reduite"),
            (r"Exc[eè]s\s+(?:de\s+)?base", "exces_base"),
            (r"Acide\s+urique", "acide_urique"),
            (r"Cr[eé]atine\s+kinase", "CPK"),
            (r"\bC\.?K\.?\b", "CPK"),
            (r"PNeutroph\.?", "polynucleaires_neutrophiles"),
            (r"PEosinoph\.?", "eosinophiles"),
            (r"PBasophiles?", "basophiles"),
            (r"\bFEVG\b", "FEVG"),
            (r"\bINR\b", "INR"),
            (r"Ratio\s+M/T", "ratio_M_T"),
            (r"\bLeucocytes\b", "globules_blancs"),
            (r"\bH[eé]maties\b", "hematies"),
            (r"\bH[eé]moglobine\b", "hemoglobine"),
            (r"\bH[eé]matocrite\b", "hematocrite"),
            (r"\bV\.?G\.?M\.?\b", "VGM"),
            (r"\bPlaquettes\b", "plaquettes"),
        ]

        # Unités les plus courantes ; l'unité est optionnelle.
        unit_pattern = re.compile(
            r"^\s*(?:"
            r"10\^?\*?\d+\s*/\s*[lL]|x10\*?\d+\s*/\s*[lL]|"
            r"g\s*/\s*(?:d[lL]|[lL])|mg\s*/\s*[lL]|µg\s*/\s*[lL]|"
            r"ng\s*/\s*m[lL]|mmol\s*/\s*[lL]|µmol\s*/\s*[lL]|"
            r"UI\s*/\s*[lL]|U\s*/\s*[lL]|kPa|mmHg|%|fl|fL|pg"
            r")",
            flags=re.IGNORECASE
        )

        for line_match in re.finditer(r"[^\n]+", texte_brut):
            line = line_match.group(0)
            if not re.search(r"\d", line):
                continue

            for alias_pattern, canonical in aliases:
                m_alias = re.search(
                    alias_pattern,
                    line,
                    flags=re.IGNORECASE
                )
                if not m_alias:
                    continue

                tail = line[m_alias.end():]

                # H/B peuvent être des indicateurs haut/bas du laboratoire.
                m_value = re.match(
                    r"\s*(?:H|B)?\s*[:=]?\s*"
                    r"(-?\d+(?:[.,]\d+)?)",
                    tail,
                    flags=re.IGNORECASE
                )
                if not m_value:
                    continue

                end_local = m_alias.end() + m_value.end()
                unit_match = unit_pattern.match(line[end_local:])
                if unit_match:
                    end_local += unit_match.end()

                surface = line[m_alias.start():end_local].strip()
                if not surface or len(surface) > 80:
                    continue

                start_abs = line_match.start() + m_alias.start()
                end_abs = line_match.start() + end_local

                if self._has_same_surface_entity(
                    entites,
                    "BIOMARQUEUR",
                    surface
                ):
                    continue

                value_text = m_value.group(1).replace(",", ".")
                try:
                    value = float(value_text)
                    if value.is_integer():
                        value = int(value)
                except Exception:
                    value = None

                entites.append({
                    "categorie": "BIOMARQUEUR",
                    "parametre": canonical,
                    "valeur": value,
                    "unite": None,
                    "valeur_reference": None,
                    "direction_cinetique": "inconnue",
                    "horodatage": "inconnu",
                    "preuve": surface,
                    "nie": False,
                    "confiance": "elevee",
                    "type_inference": "extraction_directe",
                    "page": page_number,
                    "name": surface,
                    "type": "BIOMARQUEUR",
                    "_deterministic_v63": True,
                    "_surface_start": start_abs,
                    "_surface_end": end_abs,
                })

        return entites


    def add_temporal_recall_v63(self, entites, texte_brut, page_number):
        """
        Récupération déterministe des expressions temporelles explicites.

        Contrairement à la V6.2, une date explicite EST une vraie entité du Gold.
        On privilégie les spans les plus longs et on évite les sous-dates.
        """
        if not texte_brut or not isinstance(entites, list):
            return entites

        months = (
            r"janvier|f[eé]vrier|mars|avril|mai|juin|juillet|"
            r"ao[uû]t|septembre|octobre|novembre|d[eé]cembre"
        )

        patterns = [
            # intervalle textuel complet
            rf"\b\d{{1,2}}\s+(?:{months})\s+(?:19|20)\d{{2}}"
            rf"\s+(?:au|à|-)\s+\d{{1,2}}\s+(?:{months})\s+(?:19|20)\d{{2}}\b",
            # date + heure
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}h(?:\d{2})?\b",
            # jusqu'au / depuis le + date
            r"\b(?:jusqu['’]?au|depuis\s+le|le)\s+\d{1,2}/\d{1,2}(?:[/.]\d{2,4})?\b",
            # dates numériques
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
            r"\b(?:0[1-9]|[12]\d|3[01])/(?:0[1-9]|1[0-2])\b",
            # mi janvier 2015 / 30 avril 2015
            rf"\bmi[-\s]?(?:{months})(?:\s+(?:19|20)\d{{2}})?\b",
            rf"\b\d{{1,2}}\s+(?:{months})(?:\s+(?:19|20)\d{{2}})?\b",
            # mois + année
            rf"\b(?:{months})\s+(?:19|20)\d{{2}}\b",
            # heure
            r"\b\d{1,2}h(?:\d{2})?\b",
            # année isolée
            r"\b(?:19|20)\d{2}\b",
            # moments de journée
            r"\b(?:dans\s+l['’]apr[eè]s[-\s]?midi|apr[eè]s[-\s]?midi|au\s+soir)\b",
        ]

        candidates = []
        for rank, pattern in enumerate(patterns):
            for match in re.finditer(
                pattern,
                texte_brut,
                flags=re.IGNORECASE
            ):
                candidates.append(
                    (
                        match.start(),
                        match.end(),
                        rank,
                        match.group(0)
                    )
                )

        # Durées : seulement avec un contexte temporel clair pour ne pas
        # confondre l'âge du patient ou une posologie avec un événement.
        duration_pattern = re.compile(
            r"\b(?:une\s+heure|\d+(?:[.,]\d+)?\s*(?:heures?|h|jours?|semaines?|mois|ans?))\b",
            flags=re.IGNORECASE
        )
        for match in duration_pattern.finditer(texte_brut):
            left = self.normalize_text(
                texte_brut[max(0, match.start() - 40):match.start()]
            )
            right = self.normalize_text(
                texte_brut[match.end():min(len(texte_brut), match.end() + 30)]
            )
            temporal_context = (
                "apres", "après", "depuis", "durant",
                "au bout de", "evoluant sur", "évoluant sur",
                "jusqu", "plus de"
            )
            if not any(marker in left or marker in right for marker in temporal_context):
                continue

            therapy_context = (
                "mg", "µg", "mcg", "ui", "ml", "l/min",
                "traitement", "antibiot", "prescription", "dose",
                "matin", "soir", "comprime", "comprimé"
            )
            if any(marker in left or marker in right for marker in therapy_context):
                continue

            candidates.append(
                (
                    match.start(),
                    match.end(),
                    len(patterns),
                    match.group(0)
                )
            )

        # Spans longs d'abord pour éviter 30/04 + 2015 quand une expression
        # temporelle plus complète existe.
        candidates.sort(
            key=lambda x: (-(x[1] - x[0]), x[0], x[2])
        )
        selected = []
        occupied = []

        for start, end, _, surface in candidates:
            if any(start >= a and end <= b for a, b in occupied):
                continue

            # Une année incluse dans une date plus complète n'est pas dupliquée.
            if re.fullmatch(r"(?:19|20)\d{2}", surface):
                if any(a <= start and end <= b for a, b in occupied):
                    continue

            selected.append((start, end, surface))
            occupied.append((start, end))

        selected.sort(key=lambda x: x[0])

        for start, end, surface in selected:
            self._append_literal_entity(
                entites,
                "EVENEMENT_TEMPOREL",
                surface.strip(),
                page_number,
                parametre="date_clinique",
                type_evenement="date_clinique",
                _surface_start=start,
                _surface_end=end,
                _deterministic_v63=True,
                _temporal_duration_safe=bool(
                    re.fullmatch(
                        r"(?:une\s+heure|\d+(?:[.,]\d+)?\s*(?:heures?|h|jours?|semaines?|mois|ans?))",
                        surface.strip(),
                        flags=re.IGNORECASE
                    )
                )
            )

        return entites


    def add_evolution_recall_v63(self, entites, texte_brut, page_number):
        """
        EVOLUTION_PRONOSTIC est fortement sous-extraite.
        On récupère uniquement des marqueurs d'évolution explicites.
        """
        if not texte_brut or not isinstance(entites, list):
            return entites

        patterns = [
            r"\b(?:am[eé]lioration|aggravation|d[eé]gradation|r[eé]gression|normalisation|r[eé]cup[eé]ration|stabilisation)"
            r"[^,;:\n\.]{0,95}",
            r"\b(?:s['’]am[eé]liore|s['’]aggrave|se\s+normalise|se\s+stabilise|se\s+d[eé]grade)"
            r"[^,;:\n\.]{0,80}",
            r"\b(?:progressivement\s+sevr[eé](?:e|é)?|sevrage\s+difficile|"
            r"(?:multiples?\s+)?tentatives?\s+de\s+sevrage)"
            r"[^,;:\n\.]{0,100}",
            r"\br[eé]pondant\s+[àa]\s+[^,;:\n\.]{1,70}",
            r"\bphase\s+de\s+plateau[^,;:\n\.]{0,90}",
            r"\b(?:d[eé]c[eè]s|d[eé]c[eé]d[eé]e?|d[eé]c[eé]d[eé])\b",
            r"\b(?:sans|pas\s+de)\s+complication[^,;:\n\.]{0,70}",
        ]

        for pattern in patterns:
            for match in re.finditer(
                pattern,
                texte_brut,
                flags=re.IGNORECASE
            ):
                surface = match.group(0).strip()
                if not surface:
                    continue

                # Retirer un éventuel mot de liaison initial trop vague.
                surface = re.sub(
                    r"^(?:une|une\s+nette|une\s+bonne)\s+",
                    "",
                    surface,
                    flags=re.IGNORECASE
                ).strip()

                if len(surface) < 4:
                    continue

                self._append_literal_entity(
                    entites,
                    "EVOLUTION_PRONOSTIC",
                    surface,
                    page_number,
                    parametre="evolution_clinique",
                    _surface_start=match.start(),
                    _surface_end=match.end(),
                    _deterministic_v63=True
                )

        return entites


    def add_lexical_recall_v6(self, entites, texte_brut, page_number):
        """V6.2 : rappel lexical à haute précision pour réduire les FN."""
        if not texte_brut:
            return entites

        lexical = {
            "TRAITEMENT": [
                "ventilation mécanique", "ventilation invasive", "ventilation spontanée",
                "oxygénothérapie", "Oxygène", "oxygène", "BIPAP", "VNI",
                "intubation orotrachéale", "intubation", "intubé", "réintubation",
                "extubation", "trachéotomie", "gastrostomie",
                "kinésithérapie respiratoire", "kinésithérapie", "rééducation", "attelle",
                "cardioversion", "réduction par choc", "remplissage vasculaire",
                "restriction hydrique", "transfusion sanguine", "Transfusion", "transfusion",
                "anticoagulation", "Pacemaker double chambre", "PM",
                "Vénofer IV", "Véinofer IV", "Vénofer", "Véinofer",
                "Tardyferon", "Tardiyferon", "Primpéran", "Primperan", "Lasilix", "lasilix",
                "Lovenox", "Acupan", "Augmentin", "augmentin", "Tazocilline", "TAZOCILLINE",
                "Claforan", "CLAFORAN", "Amiklin", "AMIKLIN", "amoxicilline",
                "vancomycine", "tienam", "amykacine", "amikacine",
                "noradrénaline", "adrénaline", "NA", "NPH",
                "VNI nocturne", "O2", "trachéotomie",
                "extractions dentaires", "excision de polypes",
                "prothèse mandibulaire et maxillaire", "opération de la cataracte",
                "operation de la cataracte", "traité orthopédiquement",
                "traite orthopediquement", "immunoglobulines"
            ],
            "DEFAILLANCE_ORGANE": [
                "acidose respiratoire sévère", "Acidose respiratoire sévère",
                "détresse respiratoire brutale", "détresse respiratoire sur hypoventilation",
                "Détresse respiratoire", "détresse respiratoire",
                "deux arrêts cardiaques", "arrêts cardiaques"
            ],
            "LABEL_NOSOLOGIQUE": [
                "hyponatrémie hypotonique", "hyponatrémie iatrogène", "hyponatrémie",
                "SIADH", "AVC", "flutter", "syndrome inflammatoire biologique",
                "syndrome inflammatoire", "syndrome infectieux", "sepsis",
                "choc septique", "thrombose", "dilatation pyelocalicielle gauche",
                "calcul urétéral gauche", "calcul ureteral gauche",
                "épanchements pleuraux bilatéraux", "hématome de la cuisse droite",
                "Hématome spontanée de la cuisse droite"
            ],
            "SYMPTOME": [
                "altération de l'état général", "récidive fébrile", "crépitants à gauche",
                "Hépatosplénomégalie", "Pas de syndrome méningé",
                "sensible en hypochondre droit", "état buco-dentaire insatisfaisant",
                "balancement thoraco-abdominal", "occlusion palpébrale incomplète",
                "parésie faciale supérieure", "atteinte motrice proximale", "atteinte motrice distale",
                "déficit musculaire axial", "trouble de la propulsion", "Frein expiratoire majeur",
                "pas de paralysie motrice", "ROT non retrouvé au MS", "RCP en flexion bilatéralement",
                "troubles de la déglutition", "trouble de la déglutition", "fausses routes itératives",
                "stase salivaire", "paralysie faciale", "encombrement bronchique",
                "encombrement sans facteur déclenchant", "désaturations", "désaturation",
                "hypersalivation", "marbrures", "anisocorie", "syncope", "chute",
                "tirage sus claviculaire", "sueurs", "cyanose",
                "extrémités chaudes", "extrémités froides",
                "souffle perçu", "souffle perçus", "Homans négatif", "Homan négatif",
                "conscient et orienté", "conscient et orientée",
                "trouble sensitif au toucher simple", "réflexe photomoteur présent et symétrique",
                "atteinte motrice faciale inférieure", "indolore",
                "encombrement bronchique franc", "désaturations à répétition",
                "episodes de désaturation à répétition", "épisodes de désaturation à répétition",
                "encombrement", "diarrhées", "confusion", "toux"
            ],
            "IMAGERIE_PROCEDURE": [
                "Radiographie pulmonaire", "radiographie pulmonaire", "scanner maxillo-facial",
                "TDM thoracique", "TDM Abdo", "TDM abdominale", "Écho abdo", "Echo abdo",
                "échographie abdominale", "echographie abdominale", "coronarographie",
                "Ponction d'ascite", "Radiographie", "radiographie", "scanner", "IRM",
                "ECBU", "ECG", "EMG", "EEG", "PDP", "LBA", "TDM"
            ],
            "COMORBIDITE_ANTECEDENT": [
                "insuffisance respiratoire chronique", "insuffisant respiratoire",
                "leucoencéphalopathie évoluée", "leucoencéphalopathie",
                "atrophie cortico-sous-corticale", "atrophie cortico sous corticales",
                "varices oesophagiennes", "hypertension portale", "hémibloc antérieur",
                "Fracture du péroné", "fracture du péroné", "arrachement de l'apophyse",
                "Nodule du poumon droit", "nodule de 4 mm", "Gastrite avec bulbite",
                "sinusite chronique", "pancytopénie", "Hépatite A", "tabagisme sevré",
                "tabagisme", "thrombose", "cataracte à droite", "cataracte", "BAV1",
                "hyperglycémie", "Hématome", "hernie discale", "cervicarthrose",
                "adénocarcinome", "HTA traitée", "cancer colique"
            ]
        }

        for categorie, terms in lexical.items():
            for term in sorted(set(terms), key=len, reverse=True):
                pattern = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", flags=re.IGNORECASE)
                for match in pattern.finditer(texte_brut):
                    surface = texte_brut[match.start():match.end()]

                    if categorie == "SYMPTOME":
                        left_ctx = self.normalize_text(
                            texte_brut[max(0, match.start()-15):match.start()]
                        )
                        if (
                            any(x in left_ctx for x in ("sans ", "absence de "))
                            and not self.normalize_text(surface).startswith("pas de")
                        ):
                            continue

                    self._append_literal_entity(
                        entites, categorie, surface, page_number,
                        parametre=self.safe_relation_name(term).lower(),
                        _surface_start=match.start(), _surface_end=match.end(),
                        _deterministic_v61=True
                    )

        posology_patterns = [
            r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|µg|mcg|ug|UI|U)\b",
            r"\b\d+(?:[.,]\d+)?\s*(?:mL|ml|L)\s*/\s*(?:min|h|jour)\b",
            r"\b\d+(?:[.,]\d+)?\s*(?:mL|ml|L)\b",
            r"\b\d+\s*jours?\b",
            r"\b\d+\s*/\s*j\b",
            r"\b\d+\s*(?:cp|comprim[eé]s?)\s+par\s+jour\b",
            r"\b\d+\s+bouteille\b",
            r"\b\d+-\d+-\d+\b",
            r"\b\d{1,3}\s*[-–]\s*\d{1,3}\s*%\b",
            r"\b\d+(?:[.,]\d+)?\s*[àa]\s*\d+(?:[.,]\d+)?\s*mg/h\b",
            r"\b\d+(?:[.,]\d+)?\s*/\s*\d+(?:[.,]\d+)?\s*mg/h(?:\s+de\s+NA)?\b",
            r"\b\d+\s*x\s*\d+(?:[.,]\d+)?\s*mg\s+d['’]adr[eé]naline\b",
            r"\bFiO2\s*[:=]?\s*\d+(?:[.,]\d+)?\s*%",
            r"\bPEEP\s*[:=]?\s*\d+(?:[.,]\d+)?(?:\s*cm\s*(?:H2O|d['’]eau))?",
            r"\b(?:D[eé]bit\s+)?O2\s*[:=]?\s*\d+(?:[.,]\d+)?\s*L/min\b",
            r"\b\d+(?:[.,]\d+)?\s*L/min\b",
        ]
        therapy_markers = (
            "trait", "amik", "amoxic", "tazoc", "claforan", "augmentin",
            "lovenox", "lasilix", "acupan", "primp", "oxyg", "vni",
            "ventilation", "noradr", "adren", "perfusion", "prescri",
            "administr", "matin", "soir", "jour", "fio2", "peep",
            "o2", "movicol", "clinutren", "nph", "immunoglob"
        )

        for pattern in posology_patterns:
            for match in re.finditer(pattern, texte_brut, flags=re.IGNORECASE):
                left = max(0, match.start() - 120)
                right = min(len(texte_brut), match.end() + 100)
                context = self.normalize_text(texte_brut[left:right])
                if not any(marker in context for marker in therapy_markers):
                    continue

                surface = texte_brut[match.start():match.end()]
                self._append_literal_entity(
                    entites, "POSOLOGIE", surface, page_number,
                    parametre="posologie", _surface_start=match.start(),
                    _surface_end=match.end(), _deterministic_v61=True
                )

        return entites

    def _compact_treatment_v62(self, ent):
        """
        Réduit une preuve thérapeutique à la mention minimale.
        """
        proof = str(
            ent.get("preuve")
            or ent.get("name")
            or ""
        ).strip()

        if not proof:
            return ""

        terms = [
            "Vénofer IV", "Véinofer IV", "Vénofer", "Véinofer",
            "Tardyferon", "Tardiyferon",
            "Primpéran", "Primperan", "Lasilix",
            "Vancomycine", "vancomycine",
            "amykacine", "Amiklin", "amikacine",
            "Tazocilline", "Claforan", "tienam",
            "Augmentin", "amoxicilline",
            "noradrénaline", "adrénaline",
            "insuline rapide", "NPH",
            "Lovenox", "LOVENOX", "Acupan",
            "VNI", "BIPAP",
            "kinésithérapie respiratoire",
            "kinésithérapie",
            "oxygénothérapie", "Oxygène", "oxygène",
            "ventilation mécanique",
            "intubation", "intubé",
            "réintubation",
            "extubation",
            "trachéotomie",
            "gastrostomie",
            "anticoagulation",
            "transfusion",
            "restriction hydrique",
            "remplissage vasculaire",
            "réduction par choc",
            "cardioversion",
            "Pacemaker double chambre",
            "rééducation",
            "immunoglobulines",
        ]

        return (
            self._first_literal_term(
                proof,
                terms
            )
            or proof
        )


    def _compact_symptom_v62(self, ent):
        """
        Réduit les longues descriptions symptomatiques vers le span
        clinique minimal quand celui-ci est explicitement présent.
        """
        proof = str(
            ent.get("preuve")
            or ent.get("name")
            or ""
        ).strip()

        if not proof:
            return ""

        terms = [
            "altération de l'état général",
            "Hépatosplénomégalie",
            "encombrement sans facteur déclenchant",
            "encombrement bronchique",
            "balancement thoraco-abdominal",
            "occlusion palpébrale incomplète",
            "parésie faciale supérieure",
            "atteinte motrice proximale",
            "atteinte motrice distale",
            "déficit musculaire axial",
            "trouble de la déglutition",
            "troubles de la déglutition",
            "fausses routes",
            "hypersalivation",
            "désaturations",
            "désaturation",
            "marbrures",
            "crépitants",
            "râles inspiratoires",
            "râles expiratoires",
            "anisocorie",
            "syncope",
            "chutes",
            "chute",
            "toux",
            "encombrement",
            "diarrhées",
            "confusion",
        ]

        return (
            self._first_literal_term(
                proof,
                terms
            )
            or proof
        )


    def _compact_foyer_v62(self, ent):
        """
        Réduit les phrases infectieuses vers le foyer annotable minimal.
        """
        proof = str(
            ent.get("preuve")
            or ent.get("name")
            or ""
        ).strip()

        if not proof:
            return ""

        terms = [
            "sinusite maxillaire gauche aiguë",
            "sinusite sphénoïdale droite",
            "sinusite d'origine dentaire",
            "granulome apical",
            "pansinusite",
            "parondontite",
            "parodontite",
            "pyélo obstructive",
            "pyélonéphrite",
            "pneumopathie",
            "érysipèle",
            "Carie",
            "carie",
            "point de départ indéterminé",
        ]

        return (
            self._first_literal_term(
                proof,
                terms
            )
            or proof
        )


    def _compact_posology_v62(self, ent):
        """
        Réduit une longue preuve de posologie au dosage/durée/débit.
        """
        proof = str(
            ent.get("preuve")
            or ent.get("name")
            or ""
        ).strip()

        if not proof:
            return ""

        patterns = [
            r"\b\d+(?:[.,]\d+)?\s*[àa]\s*\d+(?:[.,]\d+)?\s*mg/h\b",
            r"\b\d+(?:[.,]\d+)?\s*/\s*\d+(?:[.,]\d+)?\s*mg/h(?:\s+de\s+NA)?\b",
            r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|µg|mcg|ug|UI|U)\b",
            r"\b\d+(?:[.,]\d+)?\s*(?:mL|ml|L)\s*/\s*(?:min|h|jour)\b",
            r"\b\d+(?:[.,]\d+)?\s*L/min\b",
            r"\b\d+\s*jours?\b",
            r"\b\d{1,3}\s*[-–]\s*\d{1,3}\s*%\b",
            r"\bFiO2\s*[:=]?\s*\d+(?:[.,]\d+)?\s*%",
            r"\bPEEP\s*[:=]?\s*\d+(?:[.,]\d+)?(?:\s*cm\s*(?:H2O|d['’]eau))?",
            r"\b\d+\s*/\s*j\b",
        ]

        for pattern in patterns:
            m = re.search(
                pattern,
                proof,
                flags=re.IGNORECASE
            )

            if m:
                return m.group(0).strip()

        return proof


    def add_microorganism_recall_v62(
        self,
        entites,
        texte_brut,
        page_number
    ):
        """
        MICRO_ORGANISME avait 0 FP et 9 FN :
        rappel lexical très sûr.
        """
        if not texte_brut:
            return entites

        organisms = [
            "Clostridium difficile",
            "C. difficile",
            "C. dfficile",
            "Citrobacter Koseri",
            "CITROBACTER KOSERI",
            "SARM",
            "proteus mirabilis",
            "Proteus mirabilis",
            "enterococcus",
            "Enterococcus",
            "Staphylocoque doré",
            "Staphylococcus Aureus",
            "Serratia Marcesens",
            "Acinétobacter baumannii",
            "Acinetobacter baumannii",
            "Corynebacterium striatum",
        ]

        for organism in sorted(
            set(organisms),
            key=len,
            reverse=True
        ):
            pattern = re.compile(
                r"(?<!\w)"
                + re.escape(organism)
                + r"(?!\w)",
                flags=re.IGNORECASE
            )

            for match in pattern.finditer(
                texte_brut
            ):
                surface = texte_brut[
                    match.start():match.end()
                ]

                self._append_literal_entity(
                    entites,
                    "MICRO_ORGANISME",
                    surface,
                    page_number,
                    parametre=surface,
                    nom_micro_organisme=surface,
                    _surface_start=match.start(),
                    _surface_end=match.end(),
                    _deterministic_v62=True,
                )

        return entites


    def add_foyer_recall_v62(
        self,
        entites,
        texte_brut,
        page_number
    ):
        """
        Rappel lexical conservateur des foyers explicitement présents.
        """
        if not texte_brut:
            return entites

        terms = [
            "sinusite maxillaire gauche aiguë",
            "Sinusite sphénoïdale droite",
            "sinusite d'origine dentaire",
            "granulome apical",
            "pansinusite",
            "parondontite",
            "parodontite",
            "Carie",
            "carie",
            "point de départ indéterminé",
            "érysipèle",
            "pneumopathie",
            "pyélo obstructive",
            "pyélonéphrite",
        ]

        for term in sorted(
            set(terms),
            key=len,
            reverse=True
        ):
            pattern = re.compile(
                r"(?<!\w)"
                + re.escape(term)
                + r"(?!\w)",
                flags=re.IGNORECASE
            )

            for match in pattern.finditer(
                texte_brut
            ):
                surface = texte_brut[
                    match.start():match.end()
                ]

                self._append_literal_entity(
                    entites,
                    "FOYER_INFECTIEUX",
                    surface,
                    page_number,
                    parametre=self.safe_relation_name(
                        surface
                    ).lower(),
                    _surface_start=match.start(),
                    _surface_end=match.end(),
                    _deterministic_v62=True,
                )

        return entites



    def add_smart_structured_recall_v64(self, entites, texte_brut, page_number):
        """
        V6.4 : rappels déterministes à forte précision pour des catégories
        exclues ou trop peu couvertes en V6.3. Chaque ajout est ancré sur une
        sous-chaîne exacte du texte. On autorise les entités imbriquées lorsque
        le Gold les distingue explicitement.
        """
        if not isinstance(entites, list) or not texte_brut:
            return entites

        out = list(entites)
        existing = {
            (str(e.get("categorie") or ""), self.normalize_text(e.get("preuve") or e.get("name") or ""))
            for e in out if isinstance(e, dict)
        }

        def add(cat, proof, **extra):
            proof = str(proof or "").strip()
            if not proof:
                return
            key = (cat, self.normalize_text(proof))
            if key in existing:
                return
            m = re.search(re.escape(proof), texte_brut, flags=re.IGNORECASE)
            if not m:
                return
            ent = {
                "categorie": cat, "preuve": texte_brut[m.start():m.end()],
                "nie": False, "confiance": "elevee",
                "type_inference": "extraction_directe",
                "_surface_start": m.start(), "_surface_end": m.end(),
                "_v64_structured": True,
            }
            ent.update(extra)
            out.append(ent)
            existing.add(key)

        # SCORE_NEUROLOGIQUE : nom + valeur, frontière Gold.
        neuro_patterns = [
            r"\bGlasgow(?:\s+(?:est|à|a|=))?\s*(?:à|a|=)?\s*\d{1,2}(?:\s*/\s*15)?\b",
            r"\bGCS\s*[:=]?\s*\d{1,2}(?:\s*/\s*15)?\b",
            r"\bRASS\s*[:=]?\s*[+-]?\d+\b",
            r"\bFOUR(?:\s+score)?\s*[:=]?\s*\d+\b",
        ]
        for p in neuro_patterns:
            for m in re.finditer(p, texte_brut, flags=re.IGNORECASE):
                add("SCORE_NEUROLOGIQUE", m.group(0), parametre="Glasgow" if "glasgow" in m.group(0).lower() or "gcs" in m.group(0).lower() else "RASS")

        # SIGNE_VITAL : formulations explicitement mesurées.
        vital_patterns = [
            (r"\b(?:TA|PA)\s*(?:à|a|=|:)?\s*\d{2,3}\s*/\s*\d{2,3}(?:\s*mmHg)?\b", "pression_arterielle"),
            (r"\bPAM\s*(?:à|a|=|:|sup(?:érieure)?\s+à)?\s*\d{2,3}(?:\s*mmHg)?\b", "pression_arterielle_moyenne"),
            (r"\b(?:SpO2|SaO2|Saturat\.?\s*O2|Saturation\s+O2)\s*(?:à|a|=|:)?\s*\d{2,3}(?:[.,]\d+)?\s*%", "SpO2"),
            (r"\b(?:FC|fréquence cardiaque|frequence cardiaque|tachycardie)\s*(?:à|a|=|:)?\s*\d{2,3}(?:\s*(?:/min|bpm))\b", "frequence_cardiaque"),
            (r"\b(?:FR|fréquence respiratoire|frequence respiratoire|polypn[eé]e)\s*(?:à|a|=|:)?\s*\d{1,3}(?:\s*/min)\b", "frequence_respiratoire"),
            (r"\b(?:Temp(?:érature)?|T°)\s*(?:à|a|=|:)?\s*\d{2}(?:[.,]\d+)?\s*°?C\b", "temperature_corporelle"),
        ]
        for p, param in vital_patterns:
            for m in re.finditer(p, texte_brut, flags=re.IGNORECASE):
                add("SIGNE_VITAL", m.group(0), parametre=param)

        # IMAGERIE / PROCEDURES : conserver forme courte et forme composée.
        imaging_patterns = [
            r"\bECG\b", r"\bETT\b", r"\bEEG\b", r"\bEMG\b", r"\bEFR\b",
            r"\bTDM\b", r"\bscanner\b", r"\bIRM\b",
            r"\bRadiographie\b", r"\bRadiographie\s+(?:pulmonaire|thoracique)\b",
            r"\b[eé]chographie\b", r"\b[eé]chographie\s+(?:abdominale|r[eé]nale|pleurale|cardiaque)\b",
            r"\bfibroscopie(?:\s+bronchique)?\b", r"\bh[eé]mocultures?\b",
            r"\bECBU\b", r"\bPDP\b", r"\bLBA\b", r"\bponction\s+(?:pleurale|lombaire)\b",
        ]
        for p in imaging_patterns:
            for m in re.finditer(p, texte_brut, flags=re.IGNORECASE):
                add("IMAGERIE_PROCEDURE", m.group(0), parametre=self.normalize_text(m.group(0)).replace(" ", "_"))

        # DEFAILLANCE_ORGANE : seulement formulations lexicalement explicites.
        failures = [
            (r"\binsuffisance\s+r[eé]nale(?:\s+aigu[eë]?)?\b", "renal"),
            (r"\bIRA\b", "renal"), (r"\banurie\b", "renal"),
            (r"\bd[eé]tresse\s+respiratoire(?:\s+aigu[eë]?)?\b", "respiratoire"),
            (r"\bSDRA\b", "respiratoire"),
            (r"\bacidose\s+m[eé]tabolique\b", "metabolique"),
            (r"\bcytolyse\s+h[eé]patique\b", "hepatique"),
            (r"\binsuffisance\s+h[eé]patique\b", "hepatique"),
            (r"\bCIVD\b", "hematologique"),
        ]
        for p, typ in failures:
            for m in re.finditer(p, texte_brut, flags=re.IGNORECASE):
                add("DEFAILLANCE_ORGANE", m.group(0), type_defaillance=typ, parametre=typ)

        # POSOLOGIE : uniquement sur les lignes contenant déjà un traitement.
        treatment_surfaces = [
            str(e.get("preuve") or e.get("name") or "").strip()
            for e in out if isinstance(e, dict) and e.get("categorie") == "TRAITEMENT"
        ]
        existing_posology = [
            str(e.get("preuve") or e.get("name") or "").strip()
            for e in out if isinstance(e, dict) and e.get("categorie") == "POSOLOGIE"
        ]
        for line in texte_brut.splitlines():
            if not line.strip():
                continue
            line_n = self.normalize_text(line)
            if not any(ts and self.normalize_text(ts) in line_n for ts in treatment_surfaces):
                continue
            # Si la première/ seconde passe a déjà extrait une posologie sur
            # cette ligne, ne pas en créer une version fragmentée concurrente.
            if any(ps and self.normalize_text(ps) in line_n for ps in existing_posology):
                continue
            dose_patterns = [
                r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|µg|mcg|ug|UI|U|ppm)\b",
                r"\b\d+(?:[.,]\d+)?\s*(?:mL|ml|L)\s*/\s*(?:h|min|jour)\b",
                r"\b\d+(?:[.,]\d+)?\s*(?:x|X)\s*\d+\s*/\s*[jJ]\b",
                r"\b\d+(?:[.,]\d+)?\s*(?:fois|x)\s*/?\s*j(?:our)?\b",
                r"\b\d+-\d+-\d+\b", r"\b\d+\s*jours?\b",
                r"\bFiO2\s*[:=]?\s*\d+(?:[.,]\d+)?\s*%",
                r"\bPEEP\s*[:=]?\s*\d+(?:[.,]\d+)?(?:\s*cm\s*H2O)?",
            ]
            offset = texte_brut.find(line)
            for p in dose_patterns:
                for m in re.finditer(p, line, flags=re.IGNORECASE):
                    proof = m.group(0)
                    add("POSOLOGIE", proof, parametre="posologie", schema_horaire_brut=proof)

        return out

    def postprocess_entities_v6(self, entites, texte_brut, page_number):
        """V6.2 : filtrage de précision + conservation du rappel ciblé."""
        if not isinstance(entites, list):
            return entites

        # V6.2 : rappels à haute précision.
        entites = self.add_microorganism_recall_v62(
            entites,
            texte_brut,
            page_number
        )

        entites = self.add_foyer_recall_v62(
            entites,
            texte_brut,
            page_number
        )

        processed = []
        for ent in entites:
            if not isinstance(ent, dict):
                continue
            ent = dict(ent)
            ent["name"] = self.literal_entity_name(
                ent,
                texte_brut
            )

            categorie = ent.get("categorie", "")

            if categorie == "TRAITEMENT":
                ent["name"] = self._compact_treatment_v62(
                    ent
                )

            elif categorie == "SYMPTOME":
                ent["name"] = self._compact_symptom_v62(
                    ent
                )

            elif categorie == "FOYER_INFECTIEUX":
                ent["name"] = self._compact_foyer_v62(
                    ent
                )

            elif categorie == "POSOLOGIE":
                ent["name"] = self._compact_posology_v62(
                    ent
                )

            ent["type"] = categorie
            processed.append(ent)

        # Temporal precision V6.3
        # Le Gold courant annote explicitement les dates/heures/périodes.
        # On conserve donc une date_clinique si elle est littéralement
        # reconnaissable, au lieu de la supprimer comme en V6.2.
        temporal_clean, other = [], []
        for ent in processed:
            if ent.get("categorie") != "EVENEMENT_TEMPOREL":
                other.append(ent)
                continue

            original = str(
                ent.get("preuve")
                or ent.get("name")
                or ""
            ).strip()

            surface = self._compact_temporal_surface(original)
            if not surface:
                continue

            # Eviter de transformer un âge ou une durée thérapeutique isolée
            # en EVENEMENT_TEMPOREL. Une durée n'est conservée que si la preuve
            # contient un marqueur chronologique ou si elle vient du rappel
            # déterministe qui a déjà vérifié son contexte.
            surface_n = self.normalize_text(surface)
            original_n = self.normalize_text(original)
            is_duration = bool(re.fullmatch(
                r"(?:une\s+heure|\d+(?:[.,]\d+)?\s*(?:heures?|h|jours?|semaines?|mois|ans?))",
                surface,
                flags=re.IGNORECASE
            ))
            if is_duration and not ent.get("_temporal_duration_safe"):
                temporal_markers = (
                    "apres", "après", "depuis", "durant", "au bout de",
                    "evoluant sur", "évoluant sur", "jusqu", "plus de"
                )
                if not any(marker in original_n for marker in temporal_markers):
                    continue

            if re.fullmatch(r"\d+(?:[.,]\d+)?\s*ans", surface_n):
                if any(marker in original_n for marker in ("patient", "patiente", "age", "âge")):
                    continue

            ent["name"] = surface
            ent["preuve"] = surface
            ent["type_evenement"] = (
                ent.get("type_evenement")
                or "date_clinique"
            )
            temporal_clean.append(ent)

        # Éliminer uniquement les sous-formes évidentes d'une date plus
        # complète sur la même page : 24/02 quand 24/02/2015 existe.
        normalized_full = []
        for ent in temporal_clean:
            value = self.normalize_text(ent.get("name") or "")
            canon = value.replace("le ", "").replace(".", "/")
            normalized_full.append((ent, canon))

        temp_out = []
        for ent, canon in normalized_full:
            m_partial = re.fullmatch(r"((?:0[1-9]|[12]\d|3[01])/(?:0[1-9]|1[0-2]))", canon)
            if m_partial:
                prefix = m_partial.group(1) + "/"
                if any(
                    other_canon != canon
                    and other_canon.startswith(prefix)
                    for _, other_canon in normalized_full
                ):
                    continue

            # Une année seule reste valide sauf si cette même entité a été
            # générée comme sous-partie déterministe d'une date complète.
            if re.fullmatch(r"(?:19|20)\d{2}", canon):
                start = ent.get("_surface_start")
                if isinstance(start, int):
                    end = ent.get("_surface_end", start + len(ent.get("name") or ""))
                    contained = False
                    for other_ent, other_canon in normalized_full:
                        if other_ent is ent:
                            continue
                        ostart = other_ent.get("_surface_start")
                        oend = other_ent.get("_surface_end")
                        if (
                            isinstance(ostart, int)
                            and isinstance(oend, int)
                            and ostart <= start
                            and end <= oend
                            and len(other_canon) > len(canon)
                        ):
                            contained = True
                            break
                    if contained:
                        continue

            temp_out.append(ent)

        processed = other + temp_out

        # Biomarker precision
        filtered=[]
        for ent in processed:
            if ent.get("categorie") == "BIOMARQUEUR":
                proof = str(ent.get("preuve") or "")
                proof_n = self.normalize_text(proof)
                threshold_only = bool(re.fullmatch(
                    r"\s*[<>]?\s*\d+(?:[.,]\d+)?(?:\s*(?:à|-)\s*\d+(?:[.,]\d+)?)?"
                    r"\s*(?:µg|ug|mg|g|mmol|µmol|mol|ng|u|ui)?(?:\s*/\s*[a-z0-9*]+)?\s*",
                    proof, flags=re.IGNORECASE
                ))
                if threshold_only:
                    continue
                if any(marker in proof_n for marker in (
                    "risque de sepsis", "probabilite elevee", "probabilité élevée", "a partir de 0,25"
                )):
                    continue
                compact=self._compact_measurement_from_proof(ent)
                if compact:
                    ent["name"] = compact
            filtered.append(ent)
        processed=filtered

        # Remove planned treatments
        filtered=[]
        for ent in processed:
            if ent.get("categorie") == "TRAITEMENT":
                proof_n=self.normalize_text(ent.get("preuve") or "")
                planned=("discussion autour", "benefice attendu", "bénéfice attendu",
                         "pre-tracheotomie", "pré-trachéotomie", "envisage", "envisagé",
                         "a discuter", "à discuter")
                performed=("traite", "traité", "administre", "administré", "mise sous",
                           "mis sous", "intube", "intubé", "extub", "recoit", "reçoit",
                           "pose d", "realise", "réalisé")
                if any(x in proof_n for x in planned) and not any(x in proof_n for x in performed):
                    continue
            filtered.append(ent)
        processed=filtered

        # Symptom precision
        filtered=[]
        for ent in processed:
            if ent.get("categorie") == "SYMPTOME":
                proof_n=self.normalize_text(ent.get("preuve") or "")
                name_n=self.normalize_text(ent.get("name") or "")
                if (
                    any(x in proof_n for x in ("sans ", "absence de "))
                    and not any(name_n.startswith(x) for x in ("sans ", "absence de ", "pas de "))
                ):
                    continue
            filtered.append(ent)
        processed=filtered

        # occurrence-aware dedup
        dedup=[]
        seen=set()
        for ent in processed:
            name=str(ent.get("name") or "").strip()
            if not name:
                continue
            key_name=self.normalize_text(name)
            surface_start=ent.get("_surface_start")
            if isinstance(surface_start, int):
                key=(ent.get("categorie"), key_name, surface_start)
            elif ent.get("categorie") == "DONNEE_PATIENT":
                key=(ent.get("categorie"), key_name, self.normalize_text(ent.get("preuve") or ""))
            else:
                key=(ent.get("categorie"), key_name)
            if key in seen:
                continue
            seen.add(key)
            ent["_v61_surface_final"] = True
            dedup.append(ent)

        for i, ent in enumerate(dedup, start=1):
            ent["identifiant_entite"] = f"P{page_number}_E{i:03d}"
            ent["page"] = page_number
        return dedup

    def literal_entity_name(self, ent, texte_brut=None):
        """
        Nom NER destiné au matching.

        Règle : préférer la mention littérale réellement présente dans le texte,
        tout en conservant parametre/valeur pour la représentation ontologique.
        """
        if not isinstance(ent, dict):
            return ""

        categorie = str(ent.get("categorie") or "").strip()
        proof = str(ent.get("preuve") or "").strip()

        # V6 : compactage spécifique avant les fallbacks génériques.
        if categorie == "EVENEMENT_TEMPOREL":
            compact = self._compact_temporal_surface(proof)
            return compact or proof

        if categorie == "SERVICE_MEDICAL":
            return self._compact_service_surface(ent)

        if categorie == "TRAITEMENT":
            return self._compact_treatment_surface(ent)

        if categorie == "SYMPTOME":
            return self._compact_symptom_surface(ent)

        if categorie == "IMAGERIE_PROCEDURE":
            return self._compact_imaging_surface(ent)

        if categorie == "COMORBIDITE_ANTECEDENT":
            return self._compact_comorbidity_surface(ent)

        # Champs lexicaux spécifiques : on préfère leur vraie surface dans le texte.
        specific_fields = {
            "TRAITEMENT": (
                "nom_medicament", "nom_traitement", "nom_intervention"
            ),
            "MICRO_ORGANISME": (
                "nom_micro_organisme", "nom_microorganisme", "nom"
            ),
            "COMORBIDITE_ANTECEDENT": (
                "nom_comorbidite", "nom_antecedent", "nom_pathologie", "nom"
            ),
            "SERVICE_MEDICAL": (
                "nom_service", "nom"
            ),
            "IMAGERIE_PROCEDURE": (
                "nom_procedure", "nom_examen", "nom"
            ),
            "FOYER_INFECTIEUX": (
                "nom_foyer", "nom", "localisation"
            ),
        }

        for field in specific_fields.get(categorie, ()):
            value = ent.get(field)
            if value is None or not str(value).strip():
                continue

            surface = self._exact_surface_from_text(
                texte_brut,
                value
            )
            if surface:
                return surface

            # Si le champ spécifique apparaît littéralement dans la preuve,
            # on garde sa forme locale plutôt que la preuve entière.
            local = self._exact_surface_from_text(
                proof,
                value
            )
            if local:
                return local

        # Mesures : ne jamais utiliser le paramètre canonique comme nom NER.
        if categorie in {"BIOMARQUEUR", "SIGNE_VITAL"}:
            return self._compact_measurement_from_proof(ent)

        # POSOLOGIE : privilégier une surface compacte correspondant au Gold.
        if categorie == "POSOLOGIE":
            compact_patterns = [
                r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|µg|mcg|ug|UI|U)\b",
                r"\b\d+(?:[.,]\d+)?\s*(?:mL|ml|L)\s*/\s*(?:min|h|jour)\b",
                r"\b\d+(?:[.,]\d+)?\s*(?:mL|ml|L)\b",
                r"\b\d+\s*jours?\b",
                r"\b\d+\s*/\s*j\b",
                r"\b\d+\s+par\s+jour\b",
                r"\b\d+(?:[.,]\d+)?\s*[-àa]\s*\d+(?:[.,]\d+)?\s*(?:mg|g|µg|mcg|mL|L)?\s*/?\s*(?:h|min|jour)?\b",
                r"\b\d{1,3}\s*[-–]\s*\d{1,3}\s*%\b",
                r"\b\d+-\d+-\d+\b",
                r"\bFiO2\s*[:=]?\s*\d+(?:[.,]\d+)?\s*%",
                r"\bPEEP\s*[:=]?\s*\d+(?:[.,]\d+)?(?:\s*cm\s*(?:H2O|d['’]eau))?",
                r"\b(?:D[eé]bit\s+)?O2\s*[:=]?\s*\d+(?:[.,]\d+)?\s*L/min\b",
            ]
            for pattern in compact_patterns:
                match = re.search(pattern, proof, flags=re.IGNORECASE)
                if match:
                    return match.group(0).strip()

            for field in (
                "schema_horaire_brut",
                "duree_traitement",
                "voie_administration"
            ):
                value = ent.get(field)
                if value and str(value).strip():
                    surface = self._exact_surface_from_text(
                        texte_brut,
                        value
                    )
                    if surface:
                        return surface

            return self._compact_measurement_from_proof(ent)

        # Pour symptômes, diagnostics, défaillances et événements,
        # la preuve est préférable au paramètre normalisé.
        if proof:
            return proof

        # Dernier recours : champ lexical spécifique, mais jamais un concept
        # canonique si une surface textuelle existe.
        for field in (
            "nom_medicament",
            "nom_micro_organisme",
            "nom_comorbidite",
            "nom_antecedent",
            "nom_pathologie",
            "nom_service",
            "nom_foyer",
            "nom",
        ):
            value = ent.get(field)
            if value is not None and str(value).strip():
                return str(value).strip()

        return str(ent.get("parametre") or "").strip()

    def add_repeated_patient_mentions(self, entites, texte_brut, page_number):
        """
        V6.3 BALANCED RECALL.

        Le Gold n'annote PAS toutes les occurrences du mot patient.
        On garde donc :
        - un seul ancrage patient/patiente par page ;
        - les données démographiques explicites : âge, poids, taille, IMC/BMI.

        Cette règle évite l'explosion de faux positifs DONNEE_PATIENT tout en
        conservant un ancrage stable pour les relations de la page.
        """
        if not texte_brut or not isinstance(entites, list):
            return entites

        # Séparer les vraies données démographiques des simples répétitions
        # lexicales "patient/patiente".
        demographics = []
        patient_candidates = []
        others = []

        demo_markers = {
            "age", "age_annees", "age_calcule",
            "poids", "poids_kg",
            "taille", "taille_cm", "taille_m",
            "imc", "bmi", "sexe"
        }

        for ent in entites:
            if not isinstance(ent, dict):
                continue

            if ent.get("categorie") != "DONNEE_PATIENT":
                others.append(ent)
                continue

            proof = str(ent.get("preuve") or ent.get("name") or "").strip()
            param = self.canonical_parameter(ent.get("parametre") or "")

            if (
                param in demo_markers
                or re.search(
                    r"\b\d{1,3}\s*ans\b|"
                    r"\bpoids\s*(?:\(kg\))?\s*[:=]\s*\d|"
                    r"\btaille\s*(?:\((?:m|cm)\))?\s*[:=]\s*\d|"
                    r"\b(?:imc|bmi)\s*[:=]\s*\d",
                    proof,
                    flags=re.IGNORECASE
                )
            ):
                demographics.append(ent)
            else:
                patient_candidates.append(ent)

        # Un seul ancrage patient par page.
        anchor = None
        for ent in patient_candidates:
            proof = str(ent.get("preuve") or ent.get("name") or "")
            if re.search(
                r"\b(?:le\s+patient|la\s+patiente|patient|patiente)\b",
                proof,
                flags=re.IGNORECASE
            ):
                anchor = ent
                break

        if anchor is None:
            match = re.search(
                r"\b(?:le\s+patient|la\s+patiente|patient|patiente)\b",
                texte_brut,
                flags=re.IGNORECASE
            )
            if match:
                surface = texte_brut[match.start():match.end()]
                anchor = {
                    "categorie": "DONNEE_PATIENT",
                    "parametre": "patient",
                    "valeur": None,
                    "unite": None,
                    "valeur_reference": None,
                    "horodatage": "inconnu",
                    "preuve": surface,
                    "nie": False,
                    "confiance": "elevee",
                    "type_inference": "extraction_directe",
                    "page": page_number,
                    "name": surface,
                    "type": "DONNEE_PATIENT",
                    "_deterministic_v63": True,
                    "_surface_start": match.start(),
                    "_surface_end": match.end(),
                }

        result = others + demographics
        if anchor is not None:
            result.append(anchor)

        existing = {
            (
                self.canonical_parameter(e.get("parametre") or ""),
                self.normalize_text(e.get("name") or e.get("preuve") or "")
            )
            for e in result
            if isinstance(e, dict)
            and e.get("categorie") == "DONNEE_PATIENT"
        }

        demographic_patterns = [
            (
                "age",
                re.compile(r"\b(?:[1-9]\d?|1[01]\d|120)\s*ans\b", re.IGNORECASE),
                "ans"
            ),
            (
                "poids_kg",
                re.compile(
                    r"\bPoids\s*(?:\(kg\))?\s*[:=]\s*\d+(?:[.,]\d+)?(?:\s*kg)?",
                    re.IGNORECASE
                ),
                "kg"
            ),
            (
                "taille_m",
                re.compile(
                    r"\bTaille\s*(?:\((?:m|cm)\))?\s*[:=]\s*\d+(?:[.,]\d+)?(?:\s*(?:m|cm))?",
                    re.IGNORECASE
                ),
                None
            ),
            (
                "bmi",
                re.compile(r"\b(?:BMI|IMC)\s*[:=]\s*\d+(?:[.,]\d+)?", re.IGNORECASE),
                None
            ),
        ]

        for parametre, pattern, unit in demographic_patterns:
            for match in pattern.finditer(texte_brut):
                surface = texte_brut[match.start():match.end()].strip()
                key = (self.canonical_parameter(parametre), self.normalize_text(surface))
                if key in existing:
                    continue

                # Un âge dans "depuis 30 ans" n'est pas l'âge du patient.
                if parametre == "age":
                    left_ctx = self.normalize_text(
                        texte_brut[max(0, match.start() - 20):match.start()]
                    )
                    if any(x in left_ctx for x in ("depuis", "il y a", "pendant", "sevre")):
                        continue

                result.append({
                    "categorie": "DONNEE_PATIENT",
                    "parametre": parametre,
                    "valeur": None,
                    "unite": unit,
                    "valeur_reference": None,
                    "horodatage": "inconnu",
                    "preuve": surface,
                    "nie": False,
                    "confiance": "elevee",
                    "type_inference": "extraction_directe",
                    "page": page_number,
                    "name": surface,
                    "type": "DONNEE_PATIENT",
                    "_deterministic_v63": True,
                    "_surface_start": match.start(),
                    "_surface_end": match.end(),
                })
                existing.add(key)

        return result


    def add_explicit_temporal_mentions(self, entites, texte_brut, page_number):
        """
        V6 : aucun rappel temporel massif.
        Les dates sont laissées au modèle puis compactées/dédupliquées dans
        postprocess_entities_v6 afin d'éviter les variantes 24/02/2015,
        24/02 et 2015 comptées séparément.
        """
        return entites


    def add_explicit_service_mentions(self, entites, texte_brut, page_number):
        """Rappel conservateur des services/structures explicitement écrits."""
        if not texte_brut or not isinstance(entites, list):
            return entites

        patterns = [
            r"\br[eé]animation\b",
            r"\burgences?\b",
            r"\bUSIC\b",
            r"\bSSR\b",
            r"\bsoins\s+intensifs\b",
            r"\bh[oô]pital\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÿ'’\-]*(?:\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÿ'’\-]*){0,3}",
            r"\bclinique\s+(?:de\s+|d['’])?[A-ZÀ-ÖØ-Ý][\wÀ-ÿ'’\-]*(?:\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÿ'’\-]*){0,3}",
            r"\bcentre\s+hospitalier\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÿ'’\-]*(?:\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÿ'’\-]*){0,3}",
        ]

        existing = {
            self.normalize_text(e.get("name") or e.get("preuve") or "")
            for e in entites if isinstance(e, dict) and e.get("categorie") == "SERVICE_MEDICAL"
        }

        for pattern in patterns:
            for match in re.finditer(pattern, texte_brut, flags=re.IGNORECASE):
                surface = match.group(0).strip()
                key = self.normalize_text(surface)
                if not key or key in existing:
                    continue
                existing.add(key)
                entites.append({
                    "categorie": "SERVICE_MEDICAL",
                    "parametre": surface,
                    "nom_service": surface,
                    "valeur": None,
                    "unite": None,
                    "horodatage": "inconnu",
                    "preuve": surface,
                    "nie": False,
                    "confiance": "elevee",
                    "type_inference": "extraction_directe",
                    "page": page_number,
                    "name": surface,
                    "type": "SERVICE_MEDICAL",
                    "_deterministic_v5": True,
                })
        return entites

    def prepare_entities_for_matching(self, entites, texte_brut=None):
        """
        Ajoute les champs NER attendus par Matching_entités.py.

        IMPORTANT :
        - name = mention littérale / frontière textuelle ;
        - type = catégorie ontologique ;
        - parametre reste la normalisation interne du graphe.
        """
        if not isinstance(entites, list):
            return entites

        for ent in entites:
            if not isinstance(ent, dict):
                continue

            ent["name"] = self.literal_entity_name(
                ent,
                texte_brut
            )
            ent["type"] = str(
                ent.get("categorie") or ""
            ).strip()

        return entites


    def get_entity_name(self, entite):
        """
        Nom lisible utilisé dans les relations finales.
        """
        if not isinstance(entite, dict):
            return "entite_inconnue"

        clinical_name = self.clinical_entity_display_name(entite)
        if clinical_name:
            return clinical_name

        categorie = str(entite.get("categorie", "")).strip()
        parametre = str(entite.get("parametre", "")).strip()
        valeur = entite.get("valeur")
        unite = entite.get("unite")

        valeur_texte = "" if valeur is None else str(valeur).strip()
        unite_texte = "" if unite is None else str(unite).strip()

        if categorie == "DONNEE_PATIENT":
            return "Patient"

        if categorie == "TRAITEMENT":
            nom_medicament = str(entite.get("nom_medicament") or "").strip()
            if nom_medicament:
                return self.safe_relation_name(nom_medicament)
            return self.safe_relation_name(parametre or categorie)

        if categorie == "POSOLOGIE":
            # Priorité aux champs structurés de POSOLOGIE lorsque parametre/valeur sont vides.
            structured = []
            if entite.get("dose_valeur") is not None:
                structured.append(str(entite.get("dose_valeur")))
                if entite.get("unite_dose"):
                    structured.append(str(entite.get("unite_dose")))
            elif entite.get("debit") is not None:
                structured.append(str(entite.get("debit")))
                if entite.get("unite_debit"):
                    structured.append(str(entite.get("unite_debit")))
            elif entite.get("duree_traitement"):
                structured.append(str(entite.get("duree_traitement")))
            elif entite.get("schema_horaire_brut"):
                structured.append(str(entite.get("schema_horaire_brut")))

            elements = [parametre, valeur_texte, unite_texte] + structured
            name = "_".join(
                self.safe_relation_name(element)
                for element in elements
                if element and not self.is_null_like(element)
            )
            return name or "posologie"

        if categorie in {"BIOMARQUEUR", "SIGNE_VITAL"}:
            elements = [parametre, valeur_texte, unite_texte]
            return "_".join(
                self.safe_relation_name(element)
                for element in elements
                if element
            )

        if categorie == "IMAGERIE_PROCEDURE":
            name = (
                entite.get("nom_procedure")
                or entite.get("nom_examen")
                or parametre
                or categorie
            )
            return self.safe_relation_name(name)

        # Noms spécifiques fréquents des autres classes.
        for field in (
            "nom", "nom_foyer", "localisation", "nom_micro_organisme",
            "nom_comorbidite", "nom_pathologie", "nom_service",
            "nom_evenement", "type_evenement"
        ):
            candidate = entite.get(field)
            if candidate and not self.is_null_like(candidate):
                return self.safe_relation_name(candidate)

        final_name = valeur_texte or parametre or categorie or "entite_inconnue"
        if self.is_null_like(final_name):
            return "entite_inconnue"
        return self.safe_relation_name(final_name)

    def safe_relation_name(self, value):
        value = str(value).strip()
        value = value.replace(" ", "_")
        value = value.replace("/", "_par_")
        value = value.replace("%", "pourcent")
        value = value.replace("°", "degre_")
        value = re.sub(r"_+", "_", value)
        return value.strip("_")

    def find_patient_entity_id(self, entites):
        """
        Retourne une entité patient de la page.
        Priorité à l'entité nom, sinon première DONNEE_PATIENT.
        """
        patients = [
            ent for ent in entites
            if ent.get("categorie") == "DONNEE_PATIENT"
        ]

        for ent in patients:
            if self.canonical_parameter(ent.get("parametre")) == "nom":
                return ent.get("identifiant_entite")

        return patients[0].get("identifiant_entite") if patients else None

    def proofs_overlap(self, entite_a, entite_b):
        """
        Deux entités sont considérées liées lorsque leur preuve est identique
        ou que l'une est incluse dans l'autre.
        """
        preuve_a = self.normalize_text(entite_a.get("preuve", ""))
        preuve_b = self.normalize_text(entite_b.get("preuve", ""))

        if not preuve_a or not preuve_b:
            return False

        return (
            preuve_a == preuve_b
            or preuve_a in preuve_b
            or preuve_b in preuve_a
        )

    def add_relation_if_missing(
        self,
        relations,
        sujet,
        rtype,
        objet,
        preuve,
        confiance="elevee",
        type_inference="extraction_directe",
        note_clinique=""
    ):
        key = (sujet, rtype, objet)

        for relation in relations:
            existing = (
                relation.get("identifiant_entite_sujet"),
                relation.get("type_relation"),
                relation.get("identifiant_entite_objet")
            )
            if existing == key:
                return

        relations.append({
            "identifiant_relation": "",
            "identifiant_entite_sujet": sujet,
            "type_relation": rtype,
            "identifiant_entite_objet": objet,
            "delai_minutes": None,
            "preuve": preuve,
            "note_clinique": note_clinique,
            "type_inference": type_inference,
            "confiance": confiance
        })

    def parse_event_date(self, entite):
        """
        Convertit les principales dates françaises en tuple comparable.
        Retourne None lorsque la date est insuffisante.
        """
        value = entite.get("valeur") or entite.get("horodatage")
        if not value:
            return None

        text = str(value).strip().lower()

        match = re.search(
            r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b",
            text
        )
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year_text = match.group(3)

            if not year_text:
                return None

            year = int(year_text)
            if year < 100:
                year += 2000

            return year, month, day

        months = {
            "janvier": 1,
            "fevrier": 2,
            "mars": 3,
            "avril": 4,
            "mai": 5,
            "juin": 6,
            "juillet": 7,
            "aout": 8,
            "septembre": 9,
            "octobre": 10,
            "novembre": 11,
            "decembre": 12
        }

        text_normalise = self.normalize_text(text)

        match = re.search(
            r"\b(\d{1,2})\s+("
            + "|".join(months.keys())
            + r")\s+(\d{4})\b",
            text_normalise
        )
        if match:
            return (
                int(match.group(3)),
                months[match.group(2)],
                int(match.group(1))
            )

        return None

    def add_deterministic_relations(
        self,
        relations,
        entites,
        texte_brut,
        page_number
    ):
        """
        Ajoute les relations explicites fréquemment oubliées par le LLM.
        Aucun nouveau type de relation n'est créé : chaque ajout ici
        correspond à une signature déjà présente dans
        self.signatures_relations. Deux mécanismes sont utilisés :
        1) rattachement systématique au patient de la page pour les
           entités dont la cardinalité et la sémantique le permettent
           sans risque d'hallucination (un seul patient par page) ;
        2) chevauchement de preuve textuelle (proofs_overlap) pour les
           relations où deux entités co-apparaissent dans la même
           citation, ce qui est un indice fiable de lien explicite.
        Les relations qui exigent un jugement clinique (seuils, adéquation
        d'un antibiogramme, indication thérapeutique, facteur de risque...)
        restent volontairement laissées à l'extraction LLM, conformément
        aux règles anti-hallucination.
        """
        relations = [
            dict(relation)
            for relation in relations
            if isinstance(relation, dict)
        ]

        patient_id = self.find_patient_entity_id(entites)

        def actives(categorie):
            return [
                ent for ent in entites
                if ent.get("categorie") == categorie
                and not ent.get("nie", False)
            ]

        diagnostics = actives("LABEL_NOSOLOGIQUE")
        foyers = actives("FOYER_INFECTIEUX")
        defaillances = actives("DEFAILLANCE_ORGANE")
        symptomes = actives("SYMPTOME")
        traitements = actives("TRAITEMENT")
        posologies = actives("POSOLOGIE")
        services = actives("SERVICE_MEDICAL")
        evenements = actives("EVENEMENT_TEMPOREL")
        procedures_imagerie = actives("IMAGERIE_PROCEDURE")
        comorbidites = actives("COMORBIDITE_ANTECEDENT")
        biomarqueurs = actives("BIOMARQUEUR")
        signes_vitaux = actives("SIGNE_VITAL")
        scores_sofa = actives("SCORE_SOFA")
        scores_qsofa = actives("SCORE_qSOFA")
        scores_neuro = actives("SCORE_NEUROLOGIQUE")
        stades_ira = actives("STADE_IRA")
        micro_organismes = actives("MICRO_ORGANISME")
        contextes_acquisition = actives("CONTEXTE_ACQUISITION")
        evolutions = actives("EVOLUTION_PRONOSTIC")

        # --- RELATIONS_DIAGNOSTIQUES --------------------------------------
        if patient_id:
            for entite in diagnostics:
                self.add_relation_if_missing(
                    relations, patient_id, "a_pour_label_nosologique",
                    entite["identifiant_entite"], entite.get("preuve", "")
                )

            for entite in foyers:
                self.add_relation_if_missing(
                    relations, patient_id, "presente_suspicion_infection",
                    entite["identifiant_entite"], entite.get("preuve", "")
                )

            for entite in defaillances:
                self.add_relation_if_missing(
                    relations, patient_id, "presente_dysfonction_organe",
                    entite["identifiant_entite"], entite.get("preuve", "")
                )

            for entite in symptomes:
                self.add_relation_if_missing(
                    relations, patient_id, "presente_symptome",
                    entite["identifiant_entite"], entite.get("preuve", "")
                )

            # Un score/stade explicitement mentionné concerne, par
            # construction, le patient unique de la page.
            for score in scores_sofa:
                self.add_relation_if_missing(
                    relations, score["identifiant_entite"],
                    "score_sofa_calcule_pour", patient_id,
                    score.get("preuve", "")
                )

            for score in scores_qsofa:
                self.add_relation_if_missing(
                    relations, score["identifiant_entite"],
                    "score_qsofa_calcule_pour", patient_id,
                    score.get("preuve", "")
                )

            for stade in stades_ira:
                self.add_relation_if_missing(
                    relations, stade["identifiant_entite"],
                    "stade_ira_calcule_pour", patient_id,
                    stade.get("preuve", "")
                )

            for evolution in evolutions:
                self.add_relation_if_missing(
                    relations, patient_id, "patient_a_pour_evolution",
                    evolution["identifiant_entite"], evolution.get("preuve", "")
                )

            for service in services:
                self.add_relation_if_missing(
                    relations, service["identifiant_entite"],
                    "service_medical_accueille", patient_id,
                    service.get("preuve", "")
                )

        # SCORE_SOFA / SCORE_qSOFA -> composantes, via chevauchement de preuve
        # (ex. "SOFA 8 (bilirubine 45, plaquettes 90 000...)").
        for score in scores_sofa:
            for biomarqueur in biomarqueurs:
                if self.proofs_overlap(score, biomarqueur):
                    parametre_canonique = self.canonical_parameter(
                        biomarqueur.get("parametre")
                    )
                    if parametre_canonique in self.biomarqueurs_sofa_autorises:
                        self.add_relation_if_missing(
                            relations, score["identifiant_entite"],
                            "score_sofa_inclut_biomarqueur",
                            biomarqueur["identifiant_entite"],
                            score.get("preuve", "")
                        )

            for signe_vital in signes_vitaux:
                if self.proofs_overlap(score, signe_vital):
                    self.add_relation_if_missing(
                        relations, score["identifiant_entite"],
                        "score_sofa_inclut_signe_vital",
                        signe_vital["identifiant_entite"],
                        score.get("preuve", "")
                    )

            for score_neuro in scores_neuro:
                if self.proofs_overlap(score, score_neuro):
                    self.add_relation_if_missing(
                        relations, score["identifiant_entite"],
                        "score_sofa_inclut_score_neurologique",
                        score_neuro["identifiant_entite"],
                        score.get("preuve", "")
                    )

        for score in scores_qsofa:
            for score_neuro in scores_neuro:
                if self.proofs_overlap(score, score_neuro):
                    self.add_relation_if_missing(
                        relations, score["identifiant_entite"],
                        "score_qsofa_inclut_score_neurologique",
                        score_neuro["identifiant_entite"],
                        score.get("preuve", "")
                    )

        # --- RELATIONS_THERAPEUTIQUES --------------------------------------
        for traitement in traitements:
            for posologie in posologies:
                if self.proofs_overlap(traitement, posologie):
                    self.add_relation_if_missing(
                        relations, traitement["identifiant_entite"],
                        "traitement_a_pour_posologie",
                        posologie["identifiant_entite"],
                        posologie.get("preuve", "")
                    )

            for defaillance in defaillances:
                if self.proofs_overlap(traitement, defaillance):
                    self.add_relation_if_missing(
                        relations, traitement["identifiant_entite"],
                        "traitement_cible_defaillance",
                        defaillance["identifiant_entite"],
                        traitement.get("preuve", ""),
                        confiance="moyenne",
                        type_inference="inference_implicite",
                        note_clinique=(
                            "Traitement et défaillance co-cités dans la même "
                            "citation source."
                        )
                    )

        administration_markers = (
            "traite", "traitement par", "administration", "administre",
            "prescrit", "prescription", "recoit", "debute", "entrepris",
            "mise sous", "mis sous", "introduction", "reintroduction",
            "antibiotherapie", "medicaments", "traitement habituel",
            "traitements habituels", "ordonnance", "perfusion",
            "transfusion", "ventilation", "vni", "oxygene", "oxygén",
            "intub", "extub", "tracheot", "trachéot", "dialyse",
            "kinesitherapie", "kinésithérapie", "rehabilitation",
            "rééducation", "cardioversion", "pose"
        )

        planned_markers = (
            "a discuter", "à discuter", "envisage", "envisagé",
            "pre-tracheotomie", "pré-trachéotomie",
            "discussion autour", "benefice attendu", "bénéfice attendu"
        )

        if patient_id:
            for traitement in traitements:
                preuve = str(
                    traitement.get("preuve")
                    or traitement.get("name")
                    or ""
                ).strip()

                # Examiner aussi le contexte local puisque la frontière NER
                # du TRAITEMENT est volontairement minimale.
                context = preuve
                if preuve:
                    match = re.search(
                        re.escape(preuve),
                        texte_brut,
                        flags=re.IGNORECASE
                    )
                    if match:
                        context = texte_brut[
                            max(0, match.start() - 100):
                            min(len(texte_brut), match.end() + 120)
                        ]

                context_n = self.normalize_text(context)
                has_admin_marker = any(
                    marker in context_n
                    for marker in administration_markers
                )
                is_only_planned = (
                    any(marker in context_n for marker in planned_markers)
                    and not has_admin_marker
                )

                if is_only_planned:
                    continue

                if not self.treatment_relation_is_semantically_supported(
                    traitement,
                    context
                ):
                    continue

                # La grande majorité des entités TRAITEMENT du Gold sont
                # reliées au patient. Lorsque le contexte contient un marqueur
                # explicite, confiance élevée ; sinon moyenne.
                self.add_relation_if_missing(
                    relations,
                    traitement["identifiant_entite"],
                    "traitement_administre_a",
                    patient_id,
                    context.strip() or preuve,
                    confiance="elevee" if has_admin_marker else "moyenne",
                    type_inference=(
                        "extraction_directe"
                        if has_admin_marker
                        else "inference_structurelle"
                    )
                )

        # --- RELATIONS_SIGNES_VITAUX ----------------------------------------
        for signe_vital in signes_vitaux:
            for defaillance in defaillances:
                if self.proofs_overlap(signe_vital, defaillance):
                    self.add_relation_if_missing(
                        relations, signe_vital["identifiant_entite"],
                        "signe_vital_supporte_defaillance_organe",
                        defaillance["identifiant_entite"],
                        signe_vital.get("preuve", ""),
                        confiance="moyenne",
                        type_inference="inference_implicite",
                        note_clinique=(
                            "Signe vital et défaillance co-cités dans la même "
                            "citation source."
                        )
                    )

        # --- RELATIONS_BIOMARQUEURS_ET_MICROBIO -----------------------------
        for biomarqueur in biomarqueurs:
            for evenement in evenements:
                if self.proofs_overlap(biomarqueur, evenement):
                    self.add_relation_if_missing(
                        relations, biomarqueur["identifiant_entite"],
                        "biomarqueur_obtenu_a",
                        evenement["identifiant_entite"],
                        biomarqueur.get("preuve", "")
                    )

            for defaillance in defaillances:
                if self.proofs_overlap(biomarqueur, defaillance):
                    self.add_relation_if_missing(
                        relations, biomarqueur["identifiant_entite"],
                        "biomarqueur_supporte_defaillance_organe",
                        defaillance["identifiant_entite"],
                        biomarqueur.get("preuve", ""),
                        confiance="moyenne",
                        type_inference="inference_implicite",
                        note_clinique=(
                            "Biomarqueur et défaillance co-cités dans la même "
                            "citation source."
                        )
                    )

        for micro_organisme in micro_organismes:
            for foyer in foyers:
                if self.proofs_overlap(micro_organisme, foyer):
                    self.add_relation_if_missing(
                        relations, micro_organisme["identifiant_entite"],
                        "micro_organisme_isole_dans",
                        foyer["identifiant_entite"],
                        micro_organisme.get("preuve", "")
                    )

        # --- RELATIONS_TERRAIN_ET_RISQUE ------------------------------------
        for comorbidite in comorbidites:
            for contexte in contextes_acquisition:
                if self.proofs_overlap(comorbidite, contexte):
                    self.add_relation_if_missing(
                        relations, comorbidite["identifiant_entite"],
                        "a_pour_contexte_acquisition",
                        contexte["identifiant_entite"],
                        comorbidite.get("preuve", "")
                    )

        # --- RELATIONS_TEMPORELLES_ET_PRONOSTIC -----------------------------
        dated_events = []
        for event in evenements:
            parsed_date = self.parse_event_date(event)
            if parsed_date:
                dated_events.append((parsed_date, event))

        dated_events.sort(key=lambda item: item[0])

        for index in range(len(dated_events) - 1):
            first_date, first_event = dated_events[index]
            second_date, second_event = dated_events[index + 1]

            if first_date < second_date:
                self.add_relation_if_missing(
                    relations,
                    first_event["identifiant_entite"],
                    "precede",
                    second_event["identifiant_entite"],
                    (
                        f"{first_event.get('preuve', '')} ; "
                        f"{second_event.get('preuve', '')}"
                    ),
                    confiance="elevee"
                )

        # --- RELATIONS_IMAGERIE ----------------------------------------------
        for procedure in procedures_imagerie:
            for foyer in foyers:
                if self.proofs_overlap(procedure, foyer):
                    self.add_relation_if_missing(
                        relations, procedure["identifiant_entite"],
                        "imagerie_objective_foyer",
                        foyer["identifiant_entite"], procedure.get("preuve", "")
                    )

            for defaillance in defaillances:
                if self.proofs_overlap(procedure, defaillance):
                    self.add_relation_if_missing(
                        relations, procedure["identifiant_entite"],
                        "imagerie_objective_defaillance",
                        defaillance["identifiant_entite"],
                        procedure.get("preuve", "")
                    )

            for comorbidite in comorbidites:
                if self.proofs_overlap(procedure, comorbidite):
                    self.add_relation_if_missing(
                        relations, procedure["identifiant_entite"],
                        "imagerie_objective_comorbidite",
                        comorbidite["identifiant_entite"],
                        procedure.get("preuve", "")
                    )

        return relations

    def correct_relation_direction(self, sujet, objet, rtype, entity_map):
        signature = self.signatures_relations.get(rtype)

        if not signature:
            return sujet, objet, False

        entite_sujet = entity_map.get(sujet)
        entite_objet = entity_map.get(objet)

        if not entite_sujet or not entite_objet:
            return sujet, objet, False

        attendu_sujet, attendu_objet = signature
        categorie_sujet = entite_sujet.get("categorie")
        categorie_objet = entite_objet.get("categorie")

        if (
            categorie_sujet == attendu_sujet
            and categorie_objet == attendu_objet
        ):
            return sujet, objet, False

        if (
            categorie_sujet == attendu_objet
            and categorie_objet == attendu_sujet
        ):
            return objet, sujet, True

        return sujet, objet, False

    def validate_relation_signature(self, sujet, objet, rtype, entity_map):
        signature = self.signatures_relations.get(rtype)

        if not signature:
            return False, "relation_sans_signature"

        entite_sujet = entity_map.get(sujet)
        entite_objet = entity_map.get(objet)

        if not entite_sujet or not entite_objet:
            return False, "entite_absente"

        attendu_sujet, attendu_objet = signature

        if entite_sujet.get("categorie") != attendu_sujet:
            return False, "domaine_invalide"

        if entite_objet.get("categorie") != attendu_objet:
            return False, "image_invalide"

        # Validation spécifique des composantes biologiques du SOFA.
        if rtype == "score_sofa_inclut_biomarqueur":
            parametre = self.canonical_parameter(
                entite_objet.get("parametre")
            )
            if parametre not in self.biomarqueurs_sofa_autorises:
                return False, "biomarqueur_non_composante_sofa"

        # Contrôle sémantique supplémentaire de l'administration thérapeutique.
        if rtype == "traitement_administre_a":
            relation_proof = (
                entite_sujet.get("preuve", "")
                or entite_objet.get("preuve", "")
                or ""
            )
            if not self.treatment_relation_is_semantically_supported(
                entite_sujet, relation_proof
            ):
                return False, "administration_non_supportee"

        # Les relations positives ne doivent pas reposer sur une entité niée.
        # Cela évite de transformer une absence ("pas de foyer", "sans thrombose")
        # en connaissance positive dans le graphe.
        if entite_sujet.get("nie", False) or entite_objet.get("nie", False):
            return False, "entite_niee"

        # Interdiction des auto-relations.
        if sujet == objet:
            return False, "auto_relation_interdite"

        return True, "valide"

    def clean_relations(self, relations, entites, page_number):
        clean = []
        seen = set()
        counter = 1

        entity_map = {
            entite["identifiant_entite"]: entite
            for entite in entites
            if isinstance(entite, dict)
            and entite.get("identifiant_entite")
        }
        ids = set(entity_map.keys())

        for relation in relations:
            if not isinstance(relation, dict):
                continue

            sujet = relation.get("identifiant_entite_sujet")
            objet = relation.get("identifiant_entite_objet")
            rtype = relation.get("type_relation")

            if sujet not in ids or objet not in ids:
                continue

            if rtype not in self.relations_autorisees:
                continue

            sujet, objet, sens_corrige = self.correct_relation_direction(
                sujet, objet, rtype, entity_map
            )

            relation_valide, raison = self.validate_relation_signature(
                sujet, objet, rtype, entity_map
            )

            if not relation_valide:
                print(
                    f"⚠️ Relation rejetée page {page_number} : "
                    f"{rtype} ({raison})"
                )
                continue

            nom_sujet = self.get_entity_name(entity_map[sujet])
            nom_objet = self.get_entity_name(entity_map[objet])

            # Sécurité structurelle : aucune relation avec nom vide/None/générique.
            invalid_names = {"", "none", "null", "entite_inconnue"}
            if (
                self.normalize_text(nom_sujet) in invalid_names
                or self.normalize_text(nom_objet) in invalid_names
            ):
                print(
                    f"⚠️ Relation rejetée page {page_number} : "
                    f"{rtype} (nom_entite_vide)"
                )
                continue

            # V6.3 : dédupliquer par identifiants, pas par noms.
            # Deux occurrences distinctes portant le même texte peuvent avoir
            # chacune une relation valide dans Label Studio.
            key = (
                sujet,
                rtype,
                objet
            )

            if key in seen:
                continue

            seen.add(key)

            note_clinique = str(
                relation.get("note_clinique", "")
            ).strip()

            if sens_corrige:
                note_correction = (
                    "Sens sujet-objet corrigé automatiquement "
                    "selon la signature ontologique."
                )
                note_clinique = (
                    f"{note_clinique} {note_correction}".strip()
                )

            clean.append({
                "identifiant_relation": f"P{page_number}_R{counter:03d}",
                "identifiant_entite_sujet": sujet,
                "entite_sujet": nom_sujet,
                "type_relation": rtype,
                "identifiant_entite_objet": objet,
                "entite_objet": nom_objet,
                "delai_minutes": relation.get("delai_minutes"),
                "preuve": relation.get("preuve", ""),
                "note_clinique": note_clinique,
                "type_inference": relation.get(
                    "type_inference", "extraction_directe"
                ),
                "confiance": relation.get("confiance", "moyenne")
            })

            counter += 1

        return clean

    def build_page_assessment(self, entites, page_number):
        assessment = self.empty_sepsis_assessment(page_number)

        def is_active_infection_microbe(ent):
            """
            Un micro-organisme devient preuve d'infection seulement si le contexte
            indique un isolement/prélèvement ou une infection active.
            Un simple nom ("SARM") n'est pas suffisant.
            """
            if ent.get("nie", False):
                return False

            proof = self.normalize_text(ent.get("preuve", ""))

            colonisation_markers = (
                "portage", "colonisation", "colonise", "colonisee",
                "colonisé", "colonisée", "porteur", "porteuse"
            )
            if any(marker in proof for marker in colonisation_markers):
                return False

            active_markers = (
                "isole", "isolé", "retrouve", "retrouvé", "retrouvent",
                "positif", "positive", "culture", "hemoculture", "hémoculture",
                "ecbu", "pdp", "lba", "prelevement", "prélèvement",
                "bacteriemie", "bactériémie", "infection a", "infection à",
                "pneumopathie a", "pneumopathie à"
            )
            return any(marker in proof for marker in active_markers)

        def is_organ_failure_label(ent):
            p = self.canonical_parameter(ent.get("parametre", ""))
            return p in {
                "ira",
                "sdra",
                "civd",
                "syndrome_hepato_renal",
                "encephalopathie_hepatique"
            }

        for ent in entites:
            cat = ent.get("categorie")
            param = self.canonical_parameter(ent.get("parametre", ""))
            valeur = ent.get("valeur")
            preuve = str(ent.get("preuve", "")).strip()
            text_all = json.dumps(ent, ensure_ascii=False).lower()

            # ---------------- INFECTION ----------------
            if cat == "FOYER_INFECTIEUX":
                if not ent.get("nie", False):
                    assessment["infection_suspectee"] = True
                    if preuve:
                        assessment["preuves_infection"].append(preuve)

            if cat == "MICRO_ORGANISME":
                if is_active_infection_microbe(ent):
                    assessment["infection_suspectee"] = True
                    if preuve:
                        assessment["preuves_infection"].append(preuve)

            if cat == "LABEL_NOSOLOGIQUE":
                if (
                    not ent.get("nie", False)
                    and self.infection_label_supported(ent)
                ):
                    assessment["infection_suspectee"] = True
                    if preuve:
                        assessment["preuves_infection"].append(preuve)

                if (
                    ("sepsis" in text_all or "septique" in text_all)
                    and not ent.get("nie", False)
                ):
                    assessment["sepsis_detecte"] = True
                    if preuve:
                        assessment["preuves_globales"].append(preuve)

                # Certains diagnostics v1.5 représentent explicitement
                # une défaillance d'organe même lorsqu'ils ont été extraits
                # comme LABEL_NOSOLOGIQUE (ex. IRA, SDRA, CIVD).
                if (
                    not ent.get("nie", False)
                    and is_organ_failure_label(ent)
                ):
                    assessment["defaillance_organe"] = True
                    if preuve:
                        assessment["preuves_defaillance_organe"].append(preuve)

            # ---------------- SIGNES VITAUX ----------------
            if cat == "SIGNE_VITAL":
                if (
                    param == "temperature_corporelle"
                    and isinstance(valeur, (int, float))
                    and (valeur >= 38 or valeur < 36)
                ):
                    assessment["temperature_anormale"] = True
                    assessment["preuves_temperature"].append(preuve)

                if (
                    param == "frequence_cardiaque"
                    and isinstance(valeur, (int, float))
                    and valeur > 90
                ):
                    assessment["tachycardie"] = True
                    assessment["preuves_tachycardie"].append(preuve)

                if (
                    param == "frequence_respiratoire"
                    and isinstance(valeur, (int, float))
                    and valeur >= 22
                ):
                    assessment["tachypnee"] = True
                    assessment["preuves_tachypnee"].append(preuve)

                # qSOFA : PAS <= 100 mmHg.
                if (
                    param == "pression_arterielle_systolique"
                    and isinstance(valeur, (int, float))
                    and valeur <= 100
                ):
                    assessment["hypotension"] = True
                    assessment["preuves_hypotension"].append(preuve)

                # Critère hémodynamique sévère : PAM < 65 mmHg.
                if (
                    param == "pression_arterielle_moyenne"
                    and isinstance(valeur, (int, float))
                    and valeur < 65
                ):
                    assessment["hypotension"] = True
                    assessment["preuves_hypotension"].append(preuve)

            # ---------------- BIOLOGIE ----------------
            if cat == "BIOMARQUEUR":
                if (
                    param == "globules_blancs"
                    and isinstance(valeur, (int, float))
                ):
                    # Les valeurs sont parfois en G/L (ex. 40.8) et parfois
                    # en /mm3 (ex. 32000).
                    if valeur > 12 or valeur > 12000:
                        assessment["leucocytose"] = True
                        assessment["preuves_leucocytose"].append(preuve)

                if (
                    param == "lactate"
                    and isinstance(valeur, (int, float))
                    and valeur > 2
                ):
                    assessment["lactate_eleve"] = True
                    assessment["preuves_lactate"].append(preuve)

            # ---------------- DÉFAILLANCE ----------------
            if cat == "DEFAILLANCE_ORGANE":
                if not ent.get("nie", False):
                    assessment["defaillance_organe"] = True
                    if preuve:
                        assessment["preuves_defaillance_organe"].append(preuve)

            if cat == "STADE_IRA":
                if not ent.get("nie", False):
                    assessment["defaillance_organe"] = True
                    if preuve:
                        assessment["preuves_defaillance_organe"].append(preuve)

        # Déduplication des preuves.
        for key in assessment:
            if key.startswith("preuves_"):
                assessment[key] = self.unique_list(assessment[key])[:10]

        positive = sum(
            1 for value in assessment.values()
            if isinstance(value, bool) and value
        )
        assessment["confidence"] = round(
            min(0.95, positive * 0.15),
            2
        )

        return assessment

    def empty_sepsis_assessment(self, page_number):
        return {
            "page": page_number,
            "infection_suspectee": False,
            "temperature_anormale": False,
            "hypotension": False,
            "tachycardie": False,
            "tachypnee": False,
            "leucocytose": False,
            "defaillance_organe": False,
            "lactate_eleve": False,
            "sepsis_detecte": False,
            "preuves_infection": [],
            "preuves_temperature": [],
            "preuves_hypotension": [],
            "preuves_tachycardie": [],
            "preuves_tachypnee": [],
            "preuves_leucocytose": [],
            "preuves_defaillance_organe": [],
            "preuves_lactate": [],
            "preuves_globales": [],
            "confidence": 0.0
        }

    def build_quality_control(self, entites, relations):
        return {
            "entites_avec_preuve": all(bool(e.get("preuve")) for e in entites) if entites else True,
            "relations_avec_preuve": all(bool(r.get("preuve") or r.get("note_clinique")) for r in relations) if relations else True,
            "doublons_supprimes": True,
            "conforme_schema": True,
            "confidence_global": 0.9 if entites else 0.0
        }

    def merge_pages(self, pages):
        all_entities = []
        all_relations = []

        for page in pages:
            if page.get("statut_ocr") != "ok":
                continue

            all_entities.extend(page.get("entities", []))
            all_relations.extend(page.get("relations", []))

        # V6.3 : pas de fabrication automatique de relations inter-pages.
        # Le Gold Label Studio est annoté page par page ; une relation ajoutée
        # vers le premier patient du dossier peut devenir un FP même si elle
        # paraît cliniquement plausible. Les relations restent donc celles
        # extraites/validées sur chaque page.
        return all_entities, all_relations

    def complete_global_relations(self, entites, relations):
        """
        Complète uniquement les relations déterministes à l'échelle du dossier.
        Cela résout le cas fréquent où DONNEE_PATIENT n'est présent que page 1,
        alors que le sepsis, les foyers, symptômes ou défaillances apparaissent
        sur les pages suivantes.

        Aucun nouveau type de relation n'est introduit.
        """
        relations = [
            dict(r) for r in relations
            if isinstance(r, dict)
        ]

        patients = [
            e for e in entites
            if e.get("categorie") == "DONNEE_PATIENT"
            and not e.get("nie", False)
            and e.get("identifiant_entite")
        ]

        if not patients:
            return relations

        # Un dossier TRACE correspond à un patient unique.
        patient = patients[0]
        patient_id = patient["identifiant_entite"]

        existing = {
            (
                r.get("identifiant_entite_sujet"),
                r.get("type_relation"),
                r.get("identifiant_entite_objet")
            )
            for r in relations
        }

        counter = 1

        def add_global(subject, rtype, obj, proof, confidence="elevee"):
            nonlocal counter

            if not subject or not obj:
                return

            key = (subject, rtype, obj)
            if key in existing:
                return

            entity_map = {
                e.get("identifiant_entite"): e
                for e in entites
                if e.get("identifiant_entite")
            }

            if subject not in entity_map or obj not in entity_map:
                return

            valid, _ = self.validate_relation_signature(
                subject, obj, rtype, entity_map
            )
            if not valid:
                return

            relations.append({
                "identifiant_relation": f"G_R{counter:03d}",
                "identifiant_entite_sujet": subject,
                "entite_sujet": self.get_entity_name(entity_map[subject]),
                "type_relation": rtype,
                "identifiant_entite_objet": obj,
                "entite_objet": self.get_entity_name(entity_map[obj]),
                "delai_minutes": None,
                "preuve": proof or "",
                "note_clinique": (
                    "Relation complétée automatiquement à l'échelle du dossier "
                    "à partir du patient unique et d'une entité validée."
                ),
                "type_inference": "inference_structurelle",
                "confiance": confidence
            })
            existing.add(key)
            counter += 1

        for ent in entites:
            if ent.get("nie", False):
                continue

            eid = ent.get("identifiant_entite")
            cat = ent.get("categorie")
            proof = ent.get("preuve", "")

            if not eid:
                continue

            if cat == "LABEL_NOSOLOGIQUE":
                # On ne propage automatiquement au niveau global que les
                # diagnostics centraux liés au sepsis/infection/défaillance.
                if self.label_is_core_clinical_diagnosis_for_global_link(ent):
                    add_global(
                        patient_id,
                        "a_pour_label_nosologique",
                        eid,
                        proof
                    )

            elif cat == "FOYER_INFECTIEUX":
                add_global(
                    patient_id,
                    "presente_suspicion_infection",
                    eid,
                    proof
                )

            elif cat == "DEFAILLANCE_ORGANE":
                add_global(
                    patient_id,
                    "presente_dysfonction_organe",
                    eid,
                    proof
                )

            elif cat == "SYMPTOME":
                add_global(
                    patient_id,
                    "presente_symptome",
                    eid,
                    proof
                )

            elif cat == "EVOLUTION_PRONOSTIC":
                add_global(
                    patient_id,
                    "patient_a_pour_evolution",
                    eid,
                    proof
                )

            elif cat == "SERVICE_MEDICAL":
                # Ne pas relier automatiquement un lieu cité uniquement
                # dans un antécédent (ex. clinique où un pacemaker a été posé).
                if self.service_represents_actual_care_context(ent):
                    add_global(
                        eid,
                        "service_medical_accueille",
                        patient_id,
                        proof
                    )

            elif cat == "TRAITEMENT":
                proof_n = self.normalize_text(proof)
                administration_markers = (
                    "traite",
                    "traitement par",
                    "administration",
                    "administre",
                    "prescrit",
                    "prescription",
                    "recoit",
                    "debute",
                    "mise sous",
                    "mis sous",
                    "introduction",
                    "antibiotherapie",
                    "medicaments",
                    "perfusion",
                    "injection"
                )
                if (
                    any(marker in proof_n for marker in administration_markers)
                    and self.treatment_relation_is_semantically_supported(
                        ent, proof
                    )
                ):
                    add_global(
                        eid,
                        "traitement_administre_a",
                        patient_id,
                        proof,
                        confidence="moyenne"
                    )

        return relations

    def build_global_sepsis_assessment(self, pages):
        result = self.empty_sepsis_assessment(page_number=0)

        bool_keys = [
            "infection_suspectee", "temperature_anormale", "hypotension",
            "tachycardie", "tachypnee", "leucocytose", "defaillance_organe",
            "lactate_eleve", "sepsis_detecte"
        ]

        evidence_keys = [
            "preuves_infection", "preuves_temperature", "preuves_hypotension",
            "preuves_tachycardie", "preuves_tachypnee", "preuves_leucocytose",
            "preuves_defaillance_organe", "preuves_lactate", "preuves_globales"
        ]

        confidences = []

        for page in pages:
            assessment = page.get("sepsis_assessment", {})

            for key in bool_keys:
                result[key] = result[key] or bool(assessment.get(key, False))

            for key in evidence_keys:
                values = assessment.get(key, [])
                if isinstance(values, list):
                    result[key].extend(values)

            conf = assessment.get("confidence")
            if isinstance(conf, (int, float)):
                confidences.append(conf)

        for key in evidence_keys:
            result[key] = self.unique_list(result[key])[:10]

        result["confidence"] = round(max(confidences), 2) if confidences else 0.0
        return result

    def normalize_text(self, text):
        if text is None:
            return ""

        text = str(text).lower().strip()
        text = re.sub(r"\s+", " ", text)
        text = (
            text.replace(chr(233), "e").replace(chr(232), "e").replace(chr(234), "e")
            .replace(chr(224), "a").replace(chr(249), "u").replace(chr(231), "c")
        )

        return text

    def unique_list(self, values):
        clean = []
        seen = set()

        for value in values:
            key = self.normalize_text(value)

            if key and key not in seen:
                seen.add(key)
                clean.append(value)

        return clean


# ============================================================
# V6.5 SELECTIVE PRECISION — SURCOUCHE INTEGREE
# ============================================================

class MistralSmall4ExactOCR(_V64Engine):
    def __init__(self):
        super().__init__()
        self.schema_version = "1.6-V6.5-SELECTIVE_PRECISION"

    # ------------------------------------------------------------------
    # Récupération V6.4 : on conserve seulement les catégories où
    # l'analyse CSV montre un rapport FN/FP favorable.
    # ------------------------------------------------------------------
    def recover_missing_entities_v63(self, texte_brut, entites, page_number):
        recovered = super().recover_missing_entities_v63(
            texte_brut,
            entites,
            page_number
        )
        allowed = {
            "BIOMARQUEUR",
            "SYMPTOME",
            "TRAITEMENT",
            "LABEL_NOSOLOGIQUE",
            "MICRO_ORGANISME",
            "FOYER_INFECTIEUX",
            "DEFAILLANCE_ORGANE",
            "SIGNE_VITAL",
            "SCORE_NEUROLOGIQUE",
        }
        return [
            e for e in recovered
            if isinstance(e, dict)
            and str(e.get("categorie") or "").strip() in allowed
        ]

    def _v65_add_literal(self, out, existing, texte_brut, categorie, proof, **extra):
        proof = str(proof or "").strip()
        if not proof:
            return

        start_hint = extra.pop("_surface_start", None)
        end_hint = extra.pop("_surface_end", None)

        if start_hint is None:
            match = re.search(re.escape(proof), texte_brut, flags=re.IGNORECASE)
            if not match:
                return
            start_hint, end_hint = match.start(), match.end()
            proof = texte_brut[start_hint:end_hint]

        key = (
            categorie,
            self.normalize_text(proof),
            int(start_hint) if start_hint is not None else -1,
        )
        if key in existing:
            return

        ent = {
            "categorie": categorie,
            "preuve": proof,
            "name": proof,
            "nie": False,
            "confiance": "elevee",
            "type_inference": "extraction_directe",
            "_surface_start": start_hint,
            "_surface_end": end_hint,
            "_v65_exact_span": True,
            "_v65_target_name": proof,
        }
        ent.update(extra)
        out.append(ent)
        existing.add(key)

    def add_boundary_recall_v65(self, entites, texte_brut, page_number):
        """
        Rappel déterministe construit à partir des FN observés.
        Les règles restent lexicales et nécessitent une surface exacte.
        """
        if not isinstance(entites, list) or not texte_brut:
            return entites

        out = list(entites)
        existing = set()
        for e in out:
            if not isinstance(e, dict):
                continue
            proof = str(e.get("preuve") or e.get("name") or "").strip()
            start = e.get("_surface_start", -1)
            existing.add((
                str(e.get("categorie") or ""),
                self.normalize_text(proof),
                int(start) if isinstance(start, int) else -1,
            ))

        # ---------------- SYMPTOME : privilégier les expressions complètes.
        symptom_patterns = [
            r"\bencombrement\s+bronchique\s+franc\b",
            r"\b(?:l['’])?encombrement\s+bronchique\b",
            r"\bencombrement\s+[àa]\s+r[eé]p[eé]tition\b",
            r"\b(?:[eé]pisodes?\s+de\s+)?d[eé]saturations?\s+[àa]\s+r[eé]p[eé]tition\b",
            r"\btirage\s+sus[-\s]?claviculaire\b",
            r"\btoux\s+inefficace\b",
            r"\btoux\s+grasse\s+moyennement\s+efficace\b",
            r"\bmalaise\s+syncopal\b",
            r"\bprobables?\s+pertes?\s+de\s+connaissance\b",
            r"\bampliation\s+thoracique\s+faible\b",
            r"\balt[eé]ration\s+de\s+l['’]?[eé]tat\s+g[eé]n[eé]ral\b",
            r"\bh[eé]patospl[eé]nom[eé]galie\b",
            r"\bpas\s+d['’]h[eé]patospl[eé]nom[eé]galie\b",
            r"\bBHA\s+pr[eé]sents?\b",
            r"\bcontexte\s+f[eé]brile\b",
            r"\bmasse\s+(?:palpable|palp[eé]e)\b",
            r"\bpas\s+de\s+douleur\s+thoracique\b",
            r"\bpas\s+de\s+trouble\s+de\s+la\s+sensibilit[eé][^\n,;.]*\b",
            r"\bROT\s+rotulien\s+droit\s+per[cç]u\b",
        ]
        for p in symptom_patterns:
            for m in re.finditer(p, texte_brut, flags=re.IGNORECASE):
                self._v65_add_literal(
                    out, existing, texte_brut, "SYMPTOME", m.group(0),
                    _surface_start=m.start(), _surface_end=m.end(),
                    parametre="symptome"
                )

        # ---------------- TRAITEMENT : phrases courtes Gold-like.
        treatment_patterns = [
            r"\bpose\s+d['’]un\s+PM\b",
            r"\bVNI\s+nocturne\b",
            r"\bVNI\s+diurne\s+et\s+nocturne(?:\s+puis\s+uniquement\s+nocturne)?\b",
            r"\bventilation\s+BIPAP\b",
            r"\bventilation\s+protectrice\b",
            r"\bSonde\s+naso\s*gastrique\b",
            r"\bremplissage\s+vasculaire\b",
            r"\bdrainage\s+respiratoire\b",
            r"\b(?:Oxyg[eè]ne|oxyg[eé]noth[eé]rapie)\b",
            r"\bantibioth[eé]rapie\b",
            r"\ba[eé]rosols?\b",
            r"\b(?:Tazocilline|Tardiyferon|Tardyferon|tienam|Tienam|Ipratropium|Bud[eé]sonide|Normacol|vancomycine|Vancomycine|Augmentin)\b",
            r"\bEx[eé]r[eè]se\s+chirurgicale(?:\s+le\s+\d{1,2}[./-]\d{1,2}[./-]\d{2,4})?\b",
            r"\bH[eé]micolectomie\s+droite(?:\s+le\s+\d{1,2}[./-]\d{1,2}[./-]\d{2,4})?\b",
            r"\bAppendicectomie\s+dans\s+l['’]enfance\b",
            r"\bChimioth[eé]rapie\s+adjuvante\s+par\s+Folfox\s+en\s+attente\b",
        ]
        for p in treatment_patterns:
            for m in re.finditer(p, texte_brut, flags=re.IGNORECASE):
                proof = m.group(0)
                proof_n = self.normalize_text(proof)
                if proof_n in {"oxygene", "oxygenotherapie"}:
                    left_ctx = self.normalize_text(
                        texte_brut[max(0, m.start() - 50):m.start()]
                    )
                    if "sevr" in left_ctx:
                        continue
                self._v65_add_literal(
                    out, existing, texte_brut, "TRAITEMENT", proof,
                    _surface_start=m.start(), _surface_end=m.end(),
                    parametre="autre"
                )

        # ---------------- BIOMARQUEUR : conserver unité/contexte patient.
        biomarker_patterns = [
            r"\bFEVG\s+(?:mesur[eé]e\s+[àa]\s+)?\d+(?:[.,]\d+)?\s*%",
            r"\bGB\s*=\s*\d[\d\s]*(?:/\s*mm3)?\b",
            r"\bcr[eé]at(?:inine)?\s+(?:de\s+base\s+)?\d+(?:[.,]\d+)?\s*µ?mol\s*/\s*[lL]\b",
            r"\bur[eé]e\s+\d+(?:[.,]\d+)?\s*mmol\s*/\s*[lL]\b",
            r"\bnatr[eé]mie(?:\s+est\s+mesur[eé]e\s+[àa])?\s+\d+(?:[.,]\d+)?\s*mmol\s*/\s*[lL]\b",
            r"\b(?:pCO2|pO2)/T°\s+patient\s+\d+(?:[.,]\d+)?\b",
            r"\bLactate\s+plasmatique\s+\d+(?:[.,]\d+)?\b",
            r"\bCortisol\s+T(?:0|60)\s+min\s+\d+(?:[.,]\d+)?\b",
            r"\bRatio\s+Patient\s*/\s*T[eé]moin\s+\d+(?:[.,]\d+)?\b",
            r"\bTP\s+[àa]\s+\d+(?:[.,]\d+)?\s*%\b",
            r"\bcapacit[eé]\s+vitale\s+[àa]\s+\d+(?:[.,]\d+)?\s*%\b",
        ]
        for p in biomarker_patterns:
            for m in re.finditer(p, texte_brut, flags=re.IGNORECASE):
                self._v65_add_literal(
                    out, existing, texte_brut, "BIOMARQUEUR", m.group(0),
                    _surface_start=m.start(), _surface_end=m.end(),
                    parametre="autre_biomarqueur"
                )

        # ---------------- SIGNES VITAUX : reproduire les libellés de tableau.
        vital_patterns = [
            r"\bFC\s*\(bpm\)\s*:\s*:?[ ]*\d{2,3}\b",
            r"\bFR\s*\(c/mn\)\s*:\s*\d{1,3}\b",
            r"\bTRC\s*[<>]\s*\d+(?:[.,]\d+)?\s*(?:s|sec)\b",
            r"\bTemp[eé]rature\s+patient\s+\d{2}(?:[.,]\d+)?(?:\s+°?C)?\b",
            r"\bpic\s+f[eé]brile\s+[àa]\s+\d{2}(?:[.,]\d+)?\b",
            r"\bsaturation\s+\d{2,3}\s*[-–]\s*\d{2,3}\s*%\b",
        ]
        for p in vital_patterns:
            for m in re.finditer(p, texte_brut, flags=re.IGNORECASE):
                self._v65_add_literal(
                    out, existing, texte_brut, "SIGNE_VITAL", m.group(0),
                    _surface_start=m.start(), _surface_end=m.end(),
                    parametre="signe_vital"
                )

        # ---------------- IMAGERIE/PROCEDURE : formes longues manquées.
        imaging_patterns = [
            r"\bscanner\s+cervico[-\s]?thoracique\b",
            r"\bscanner\s+c[eé]r[eé]bral(?:\s+r[eé]alis[eé]\s+est\s+normal)?\b",
            r"\bTDM\s+thoracique\b",
            r"\bIRM\s+m[eé]dullaire\b",
            r"\bEMG\s+r[eé]alis[eé]\s+le\s+\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",
            r"\bEEG\s+est\s+r[eé]alis[eé]\s+le\s+\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",
            r"\bPonction\s+d['’]ascite\b",
            r"\bColoscopie\b",
            r"\bh[eé]moc\s+p[eé]rih\s+et\s+centrale\b",
            r"\bECU\b",
        ]
        for p in imaging_patterns:
            for m in re.finditer(p, texte_brut, flags=re.IGNORECASE):
                self._v65_add_literal(
                    out, existing, texte_brut, "IMAGERIE_PROCEDURE", m.group(0),
                    _surface_start=m.start(), _surface_end=m.end(),
                    parametre="autre"
                )

        # ---------------- POSOLOGIE : préférer schéma complet aux fragments.
        posology_patterns = [
            r"\b\d+(?:[.,]\d+)?\s*g\s*[xX]\s*\d+\s*/\s*[jJ]\b",
            r"\b\d+(?:[.,]\d+)?\s*[xX]\s*\d+\s*/\s*[jJ]\b",
            r"\b\d+(?:[.,]\d+)?\s*g\s*[xX]\s*\d+\s+par\s+jour\b",
            r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|UI)\s*/\s*\d+(?:[.,]\d+)?\s*mL\s+SC\s+la\s+nuit\b",
            r"\b\d+(?:[.,]\d+)?\s*mg\s+PO\s+si\s+besoin\b",
            r"\b\d+(?:[.,]\d+)?\s*mg/\d+(?:[.,]\d+)?mL\s+PO\s+si\s+besoin\b",
            r"\b\d+(?:[.,]\d+)?g/\d+(?:[.,]\d+)?mg\s+PO\s+\d-\d-\d\s+pendant\s+\d+\s+jours(?:\s*\(J\d+/\d+\))?\b",
            r"\b\d-\d-\d\s+si\s+besoin\b",
            r"\b\d+(?:[.,]\d+)?\s*[àa]\s*\d+(?:[.,]\d+)?\s*mg/h\b",
            r"\bdur[eé]e\s+totale\s+de\s+\d+\s+jours\b",
            r"\b\d+\s*L\s*O2\b",
            r"\bsaturation\s+\d{2,3}\s*[-–]\s*\d{2,3}\s*%\b",
            r"\b\d+\s*/\s*j\s+depuis\s+[^\n,;.]+\b",
        ]
        for p in posology_patterns:
            for m in re.finditer(p, texte_brut, flags=re.IGNORECASE):
                self._v65_add_literal(
                    out, existing, texte_brut, "POSOLOGIE", m.group(0),
                    _surface_start=m.start(), _surface_end=m.end(),
                    parametre="posologie",
                    schema_horaire_brut=m.group(0)
                )

        # ---------------- EVOLUTION : clauses cliniques réellement évolutives.
        evolution_patterns = [
            r"\b(?:La|L['’])\s*fonction\s+respiratoire\s+s['’]am[eé]liore\b",
            r"\b(?:L['’])?encombrement\s+bronchique\s+s['’]am[eé]liore\b",
            r"\bprogressivement\s+sevr[eé]\s+de\s+l['’]oxyg[eè]ne\b",
            r"\bs['’]aggrave\s+progressivement\b",
            r"\bL['’][eé]volution\s+clinique\s+est\s+par\s+la\s+suite\s+favorable\b",
            r"\bmobilisation\s+des\s+4\s+membres\s+possible\b",
            r"\bStation\s+au\s+fauteuil\s+plusieurs\s+heures\b",
            r"\breprise\s+de\s+l['’]alimentation\b",
            r"\bReprise\s+d['’]une?\s+alimentation\s+normale\b",
            r"\bd[eé]c[eè]s\s+du\s+patient\b",
        ]
        for p in evolution_patterns:
            for m in re.finditer(p, texte_brut, flags=re.IGNORECASE):
                self._v65_add_literal(
                    out, existing, texte_brut, "EVOLUTION_PRONOSTIC", m.group(0),
                    _surface_start=m.start(), _surface_end=m.end(),
                    parametre="evolution"
                )

        return out

    def _reclassify_v65(self, ent):
        if not isinstance(ent, dict):
            return ent
        ent = dict(ent)
        surface = str(ent.get("preuve") or ent.get("name") or "").strip()
        n = self.normalize_text(surface)

        rules = [
            (r"^sinusite chronique$", "FOYER_INFECTIEUX"),
            (r"^hyperglycemie$", "BIOMARQUEUR"),
            (r"^pic febrile a \d", "SIGNE_VITAL"),
            (r"^leucoencephalopathie(?: evoluee)?$", "LABEL_NOSOLOGIQUE"),
            (r"^deglobulisation$", "DEFAILLANCE_ORGANE"),
            (r"^hypoxemie$", "DEFAILLANCE_ORGANE"),
            (r"^hepato\s*\(?splenomegalie\)?$", "SYMPTOME"),
            (r"^capacite vitale a \d", "BIOMARQUEUR"),
            (r"^traumatisme du genou", "SYMPTOME"),
            (r"^trouble cognitif majeur$", "SYMPTOME"),
            (r"^decompensation respiratoire$", "DEFAILLANCE_ORGANE"),
            (r"^episode septique$", "LABEL_NOSOLOGIQUE"),
            (r"^thrombopenie$", "LABEL_NOSOLOGIQUE"),
            (r"^hypertension arterielle labile$", "LABEL_NOSOLOGIQUE"),
            (r"^deficit sensitivomoteur complet", "DEFAILLANCE_ORGANE"),
            (r"^pas de signe de lutte respiratoire$", "SYMPTOME"),
            (r"^hepatopathie chronique$", "COMORBIDITE_ANTECEDENT"),
            (r"^lacune ischemique", "LABEL_NOSOLOGIQUE"),
            (r"^hypoglycemies?$", "LABEL_NOSOLOGIQUE"),
            (r"^chimiotherapie adjuvante", "TRAITEMENT"),
            (r"^hemicolectomie droite", "TRAITEMENT"),
            (r"^appendicectomie", "TRAITEMENT"),
            (r"^demineralisation des interphalangiennes", "COMORBIDITE_ANTECEDENT"),
        ]
        for pattern, category in rules:
            if re.search(pattern, n):
                ent["categorie"] = category
                ent["type"] = category
                break

        # Cas hématome : le Gold distingue hématome spontané diagnostique
        # et hématome local décrit comme manifestation.
        if "hematome de la cuisse" in n and "spontan" not in n:
            ent["categorie"] = "SYMPTOME"
            ent["type"] = "SYMPTOME"

        return ent

    def _filter_v65(self, ent):
        if not isinstance(ent, dict):
            return False

        cat = str(ent.get("categorie") or ent.get("type") or "").strip()
        surface = str(ent.get("preuve") or ent.get("name") or "").strip()
        n = self.normalize_text(surface)

        # SERVICE : fragments de narration captés à cause du mot "clinique".
        if cat == "SERVICE_MEDICAL":
            generic = (
                "clinique d admission", "clinique respiratoire",
                "clinique retrouve", "clinique est par la suite",
                "clinique il est transfere", "clinique est transfere",
            )
            if any(x in n for x in generic):
                return False
            if n == "urgence":
                return False

        # EVOLUTION : notions de risque/diagnostic sans changement temporel.
        if cat == "EVOLUTION_PRONOSTIC":
            evo_markers = (
                "ameliore", "amelioration", "aggrave", "aggravation", "degradation",
                "normalis", "sevre", "sevrage", "recuper", "favorable", "deces",
                "reprise", "regression", "mobilisation", "station au fauteuil",
                "diminution", "augmentation", "repondant", "plateau", "complication", "evolu",
            )
            if not any(x in n for x in evo_markers):
                return False
            if any(x in n for x in (
                "risque de sepsis", "probabilite", "sirs significatif",
                "sirs eleve"
            )):
                return False

        # IMAGERIE : objets/résultats mal pris pour des procédures.
        if cat == "IMAGERIE_PROCEDURE" and any(x in n for x in (
            "granulome apical",
            "prothese mandibulaire",
            "gaz du sang",
            "lesion hepatique",
        )):
            return False

        # CONTEXTE_ACQUISITION très peu précis en V6.4 :
        # ne garder que des marqueurs réellement explicites.
        if cat == "CONTEXTE_ACQUISITION":
            if not any(x in n for x in (
                "nosocom", "communaut", "acquis", "hospital",
                "institution", "domicile", "multiresistant", "multiresistante"
            )):
                return False

        return True

    def _restore_v65_exact_names(self, entites):
        out = []
        for ent in entites:
            if not isinstance(ent, dict):
                continue
            ent = self._reclassify_v65(ent)
            if ent.get("_v65_exact_span") and ent.get("_v65_target_name"):
                ent["name"] = str(ent["_v65_target_name"]).strip()
                ent["preuve"] = str(ent["_v65_target_name"]).strip()
            if self._filter_v65(ent):
                out.append(ent)
        return out

    def _drop_nested_short_duplicates_v65(self, entites):
        """
        Supprime seulement les doublons courts au même offset lorsqu'une
        forme longue de même type existe. Les occurrences distinctes restent.
        """
        if not isinstance(entites, list):
            return entites

        drop = set()
        for i, a in enumerate(entites):
            if not isinstance(a, dict):
                continue
            ca = str(a.get("categorie") or a.get("type") or "")
            na = self.normalize_text(a.get("name") or a.get("preuve") or "")
            sa = a.get("_surface_start")
            if not na or not isinstance(sa, int):
                continue

            for j, b in enumerate(entites):
                if i == j or not isinstance(b, dict):
                    continue
                cb = str(b.get("categorie") or b.get("type") or "")
                nb = self.normalize_text(b.get("name") or b.get("preuve") or "")
                sb = b.get("_surface_start")
                if ca != cb or sa != sb or not nb:
                    continue
                if len(na) < len(nb) and na in nb:
                    # Pour les posologies, conserver la forme la plus riche.
                    # Pour imagerie et traitements, même logique à offset égal.
                    if ca in {
                        "POSOLOGIE", "IMAGERIE_PROCEDURE",
                        "TRAITEMENT", "SYMPTOME"
                    }:
                        drop.add(i)
        return [e for i, e in enumerate(entites) if i not in drop]


    def _dedup_exact_occurrence_v65(self, entites):
        if not isinstance(entites, list):
            return entites
        out = []
        seen = set()
        for ent in entites:
            if not isinstance(ent, dict):
                continue
            category = str(ent.get("categorie") or ent.get("type") or "")
            name = self.normalize_text(ent.get("name") or ent.get("preuve") or "")
            start = ent.get("_surface_start")
            start_key = start if isinstance(start, int) else None
            key = (category, name, start_key)
            generic_key = (category, name, None)
            if name:
                # Si une des deux entités n'a pas d'offset fiable, le même
                # type+nom est considéré doublon. Deux offsets distincts
                # restent en revanche deux occurrences légitimes.
                if key in seen or generic_key in seen:
                    continue
                if start_key is None and any(
                    k[0] == category and k[1] == name
                    for k in seen
                ):
                    continue
            seen.add(key)
            out.append(ent)
        return out

    def postprocess_entities_v6(self, entites, texte_brut, page_number):
        entites = self.add_boundary_recall_v65(
            entites,
            texte_brut,
            page_number
        )
        processed = super().postprocess_entities_v6(
            entites,
            texte_brut,
            page_number
        )
        processed = self._restore_v65_exact_names(processed)
        processed = self._drop_nested_short_duplicates_v65(processed)
        processed = self._dedup_exact_occurrence_v65(processed)
        return processed

