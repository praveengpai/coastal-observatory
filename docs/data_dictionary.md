# Data dictionary

Generated from the ODK forms in `forms/dist`. Field names here are the column names in exports and the keys stored in the database. Do not rename a field once data has been collected.

## obs_camp_registration

| Field | Type | Question (English) | Shown when | Calculation |
| --- | --- | --- | --- | --- |
| `camp_gps` | start-geopoint |  |  |  |
| `camp_site` | select_one_from_file sites.csv | Site |  |  |
| `role` | select_one reg_role | Your role today |  |  |
| `site_type` | calculate |  |  | instance('sites')/root/item[name=${camp_site}]/site_type |
| `camp_id` | calculate |  |  | concat(${camp_site}, '-', format-date(today(), '%Y%m%d')) |
| `consent_research` | select_one yes_no | May we use this information, without names, for the water and health study? Care is the same whether or not you agree. |  |  |
| `pid_method` | select_one id_method | Person ID: scan or type? |  |  |
| `pid_scan` | barcode | Scan the person ID sticker on the health card | ${pid_method}='scan' |  |
| `pid_type` | text | Type the person ID | ${pid_method}='type' |  |
| `person_id` | calculate |  |  | if(${pid_method}='scan', ${pid_scan}, ${pid_type}) |
| `hh_method` | select_one id_method | Household ID: scan or type? |  |  |
| `hh_scan` | barcode | Scan the household sticker | ${hh_method}='scan' |  |
| `hh_type` | text | Type the household ID | ${hh_method}='type' |  |
| `hh_id` | calculate |  |  | if(${hh_method}='scan', ${hh_scan}, ${hh_type}) |
| `name` | text | Name |  |  |
| `age` | integer | Age (years) |  |  |
| `sex` | select_one sex | Sex |  |  |
| `phone` | text | Phone number (for results) |  |  |
| `resident` | select_one yes_no | Does this person live here permanently? |  |  |
| `home_address` | text | Home address |  |  |
| `home_lsg` | text | Panchayat / municipality / ward |  |  |
| `stay` | select_one stay | How long staying here? |  |  |
| `first_member` | select_one yes_no | Is this the first person from this household registered at this camp? | ${consent_research}='yes' and ${resident}='yes' |  |
| `hh_size` | integer | Number of people living in this house |  |  |
| `hh_n60` | integer | How many are aged 60 or above? |  |  |
| `hh_n5` | integer | How many children under 5? |  |  |
| `water_drink` | select_one water_src | Main source of drinking water |  |  |
| `cook_same` | select_one yes_no | Same water used for cooking? |  |  |
| `water_cook` | select_one water_src | Water for cooking | ${cook_same}='no' |  |
| `treat` | select_multiple treat | How is drinking water treated? |  |  |
| `storage` | select_one storage | How is drinking water stored? |  |  |
| `salty` | select_one freq3 | Does your well or tap water ever taste salty? |  |  |
| `salty_season` | select_multiple season | In which season? | ${salty}!='never' |  |
| `toilet` | select_one toilet | Type of toilet |  |  |
| `septic_dist` | select_one dist | Distance from septic tank or pit to the well | selected(${water_drink}, 'own_well') or selected(${water_drink}, 'shared_well') |  |
| `flood` | select_one yes_no | In the past 12 months, did water enter the house or compound? |  |  |
| `flood_times` | integer | How many times? | ${flood}='yes' |  |
| `animals` | select_multiple animals | Animals or birds kept at home |  |  |
| `rats` | select_one freq3 | Do you see rats around the house or water storage? |  |  |
| `sump_mgr` | select_one sump_mgr | Who manages the sump and tank? |  |  |
| `tank_clean` | select_one last_clean | When was the tank last cleaned? |  |  |
| `bottle` | select_one yes_no | Did they bring a bottle of their drinking water? |  |  |
| `tds` | integer | TDS meter reading (mg/L) | ${bottle}='yes' |  |
| `occupation` | select_one occ | Main occupation | ${age} >= 15 |  |
| `wade` | select_one yes_no | In the past month, walked through flood or canal water? |  |  |
| `sx` | select_multiple sx | In the past 2 weeks, any of these? |  |  |
| `sx_days` | integer | Days unwell | count-selected(${sx}) > 0 and not(selected(${sx}, 'none')) |  |
| `sx_care` | select_one sx_care | Treatment taken | count-selected(${sx}) > 0 and not(selected(${sx}, 'none')) |  |
| `sx_missed` | select_one yes_no | Missed work or school? | count-selected(${sx}) > 0 and not(selected(${sx}, 'none')) |  |
| `conditions` | select_multiple cond | Known illnesses |  |  |
| `meds` | text | Medicines taken now | not(selected(${conditions}, 'none')) |  |
| `tobacco` | select_one tob | Tobacco, paan or areca use | ${age} >= 12 |  |
| `contact_ok` | select_one yes_no | May we phone you with your results? | string-length(${phone}) > 0 |  |

## obs_camp_station

| Field | Type | Question (English) | Shown when | Calculation |
| --- | --- | --- | --- | --- |
| `camp_gps` | start-geopoint |  |  |  |
| `camp_site` | select_one_from_file sites.csv | Site |  |  |
| `role` | select_one station | Your station today |  |  |
| `site_type` | calculate |  |  | instance('sites')/root/item[name=${camp_site}]/site_type |
| `camp_id` | calculate |  |  | concat(${camp_site}, '-', format-date(today(), '%Y%m%d')) |
| `pid_method` | select_one id_method | Person ID: scan or type? |  |  |
| `pid_scan` | barcode | Scan the person ID sticker on the health card | ${pid_method}='scan' |  |
| `pid_type` | text | Type the person ID | ${pid_method}='type' |  |
| `person_id` | calculate |  |  | if(${pid_method}='scan', ${pid_scan}, ${pid_type}) |
| `age` | integer | Age, from the health card |  |  |
| `bp1_sys` | integer | 1st reading: systolic (upper) |  |  |
| `bp1_dia` | integer | 1st reading: diastolic (lower) |  |  |
| `bp2_sys` | integer | 2nd reading after 5 minutes: systolic |  |  |
| `bp2_dia` | integer | 2nd reading: diastolic |  |  |
| `sbp` | calculate |  |  | round((${bp1_sys} + ${bp2_sys}) div 2, 0) |
| `dbp` | calculate |  |  | round((${bp1_dia} + ${bp2_dia}) div 2, 0) |
| `glucose` | integer | Capillary glucose (mg/dL) |  |  |
| `glu_type` | select_one glu_type | Fasting or random? |  |  |
| `height` | decimal | Height (cm) |  |  |
| `weight` | decimal | Weight (kg) |  |  |
| `bmi` | calculate |  |  | round(${weight} div ((${height} div 100) * (${height} div 100)), 1) |
| `urine_done` | select_one yes_no | Urine test done? |  |  |
| `u_protein` | select_one dip | Protein | ${urine_done}='yes' |  |
| `u_glucose` | select_one dip | Glucose | ${urine_done}='yes' |  |
| `u_blood` | select_one dip | Blood | ${urine_done}='yes' |  |
| `u_leuk` | select_one dip | Leukocytes | ${urine_done}='yes' |  |
| `u_nitrite` | select_one posneg | Nitrite | ${urine_done}='yes' |  |
| `u_sg` | decimal | Specific gravity | ${urine_done}='yes' |  |
| `spo2` | integer | SpO2 (%) |  |  |
| `pulse` | integer | Pulse (per minute) |  |  |
| `hb` | decimal | Haemoglobin (g/dL), if a meter is available |  |  |
| `eye_far` | select_one yes_no | Difficulty seeing far? |  |  |
| `eye_near` | select_one yes_no | Difficulty seeing near or reading? |  |  |
| `glasses` | select_one yes_no | Uses glasses now? |  |  |
| `last_eye` | select_one last_check | Last eye check |  |  |
| `dm_known` | select_one yes_no | Diabetic? (from the card) |  |  |
| `glucose_card` | integer | Blood sugar on the card (mg/dL), if done |  |  |
| `dm_years` | integer | Years since diabetes was diagnosed | ${dm_known}='yes' |  |
| `retina_ever` | select_one yes_no | Retina ever checked? | ${dm_known}='yes' |  |
| `eye_water` | select_one yes_no | Red or sticky eyes after flood or canal water? |  |  |
| `va_r` | select_one va | Distance vision, right eye |  |  |
| `va_l` | select_one va | Distance vision, left eye |  |  |
| `pinhole_better` | select_one yes_no | Improves with pinhole? | ${va_r}!='6_6' or ${va_l}!='6_6' |  |
| `near_ok` | select_one yes_no | Near vision normal (N6 at 40 cm)? | ${age} >= 40 |  |
| `readers_given` | select_one yes_no | Reading glasses given? | ${near_ok}='no' |  |
| `cataract` | select_one sides | Cataract | ${age} >= 40 |  |
| `fundus_needed` | calculate |  |  | if(${dm_known}='yes' or ${glucose_card} >= 200, 'yes', 'no') |
| `fundus_done` | select_one yes_no | Fundus photo taken? |  |  |
| `fundus_img` | text | Image ID in the camera app | ${fundus_done}='yes' |  |
| `dr_r` | select_one dr | DR grade, right eye | ${fundus_done}='yes' |  |
| `dr_l` | select_one dr | DR grade, left eye | ${fundus_done}='yes' |  |
| `dme` | select_one yes_no | Macular oedema suspected? | ${fundus_done}='yes' |  |
| `iop_r` | decimal | Eye pressure right (mmHg), if measured | ${age} >= 40 |  |
| `iop_l` | decimal | Eye pressure left (mmHg), if measured | ${age} >= 40 |  |
| `eye_referral` | select_one eye_ref | Eye referral |  |  |
| `oral_sx` | select_multiple oral_sx | Any of these now? |  |  |
| `brush` | select_one brush | How often do you brush? | ${age} >= 5 |  |
| `last_dental` | select_one last_check | Last dental visit |  |  |
| `tob_d` | select_one tob | Tobacco, paan or areca use | ${age} >= 12 |  |
| `caries_n` | integer | Number of decayed teeth |  |  |
| `missing_n` | integer | Number of missing teeth |  |  |
| `gum` | select_one sev4 | Gum disease |  |  |
| `hygiene` | select_one hyg | Oral hygiene |  |  |
| `lesion` | select_one lesion | Suspicious oral lesion | ${age} >= 30 or ${tob_d}='current' |  |
| `fluorosis` | select_one dean | Dental fluorosis (Dean's index) | ${age} >= 8 and ${age} <= 15 |  |
| `dent_referral` | select_one dent_ref | Dental referral |  |  |
| `alone` | select_one yes_no | Lives alone? |  |  |
| `carer` | select_one yes_no | Someone available to help when needed? |  |  |
| `evac` | select_one yes_no | Would need help to leave home in a flood? |  |  |
| `heat_sx` | select_one yes_no | Felt dizzy or very tired on hot days this year? |  |  |
| `falls` | integer | Falls in the past 12 months |  |  |
| `cfs` | select_one cfs | Clinical Frailty Scale |  |  |
| `mc_words` | select_one n0to3 | Words recalled |  |  |
| `mc_clock` | select_one yes_no | Clock drawn correctly? |  |  |
| `minicog_score` | calculate |  |  | number(${mc_words}) + if(${mc_clock}='yes', 2, 0) |
| `whisper_r` | select_one passfail | Right ear |  |  |
| `whisper_l` | select_one passfail | Left ear |  |  |
| `phq1` | select_one phq | In the past 2 weeks: little interest or pleasure in doing things? |  |  |
| `phq2` | select_one phq | Feeling down, depressed or hopeless? |  |  |
| `phq2_score` | calculate |  |  | number(${phq1}) + number(${phq2}) |
| `grip` | decimal | Grip strength, best hand (kg), if a dynamometer is available |  |  |
| `dx` | select_multiple dx | Diagnosis |  |  |
| `dx_other` | text | Other diagnosis | selected(${dx}, 'other') |  |
| `doc_notes` | text | Notes and treatment |  |  |
| `doc_referral` | select_one doc_ref | Referral |  |  |
| `ref_reason` | text | Reason for referral | ${doc_referral}!='none' |  |
| `followup` | select_one yes_no | Follow-up needed by ASHA? |  |  |

## obs_household_visit

| Field | Type | Question (English) | Shown when | Calculation |
| --- | --- | --- | --- | --- |
| `camp_gps` | start-geopoint |  |  |  |
| `camp_site` | select_one_from_file sites.csv | Site |  |  |
| `role` | select_one field_role | Your role today |  |  |
| `site_type` | calculate |  |  | instance('sites')/root/item[name=${camp_site}]/site_type |
| `camp_id` | calculate |  |  | concat(${camp_site}, '-', format-date(today(), '%Y%m%d')) |
| `hh_method` | select_one id_method | Household ID: scan or type? |  |  |
| `hh_scan` | barcode | Scan the household sticker | ${hh_method}='scan' |  |
| `hh_type` | text | Type the household ID | ${hh_method}='type' |  |
| `hh_id` | calculate |  |  | if(${hh_method}='scan', ${hh_scan}, ${hh_type}) |
| `reason` | select_multiple visit_reason | Reason for this visit |  |  |
| `anyone_ill` | select_one yes_no | Was anyone in the house ill in the past 2 weeks? |  |  |
| `n_diarrhoea` | integer | People with loose stools 3+ times a day | ${anyone_ill}='yes' |  |
| `n_diarrhoea_u5` | integer | Of these, children under 5 | ${anyone_ill}='yes' and ${n_diarrhoea} > 0 |  |
| `n_fever` | integer | People with fever | ${anyone_ill}='yes' |  |
| `n_jaundice` | integer | People with yellow eyes | ${anyone_ill}='yes' |  |
| `n_skin` | integer | Skin rash or boils | ${anyone_ill}='yes' |  |
| `n_eye` | integer | Red or sticky eyes | ${anyone_ill}='yes' |  |
| `n_wound` | integer | Wound infected after water contact | ${anyone_ill}='yes' |  |
| `n_heat` | integer | Elders 60+ dizzy or exhausted in the heat | ${anyone_ill}='yes' |  |
| `n_hosp` | integer | Admitted to hospital | ${anyone_ill}='yes' |  |
| `ref_person` | text | Person ID on the health card |  |  |
| `ref_status` | select_one ref_status | Did they go to the referral? |  |  |
| `ref_barrier` | select_multiple barrier | What stopped them? | ${ref_status}='not_yet' or ${ref_status}='refused' |  |
| `eld_checked` | integer | Elders 60+ checked in this house |  |  |
| `eld_meds` | select_one yes_no | Medicines for at least 5 days at home? |  |  |
| `eld_phone` | select_one yes_no | A charged phone with the ASHA's number? |  |  |
| `eld_evac` | select_one yes_no | Needs help to move out if water rises? |  |  |
| `eld_water` | select_one yes_no | Drinking enough water, has shade or a fan? |  |  |
| `advice` | select_multiple advice | Advice or results given today |  |  |
| `chlorine_given` | integer | Chlorine tablets given | selected(${advice}, 'chlorinate') |  |
| `notes` | text | Notes |  |  |

## obs_water_sample

| Field | Type | Question (English) | Shown when | Calculation |
| --- | --- | --- | --- | --- |
| `camp_gps` | start-geopoint |  |  |  |
| `camp_site` | select_one_from_file sites.csv | Site |  |  |
| `role` | select_one field_role | Your role today |  |  |
| `site_type` | calculate |  |  | instance('sites')/root/item[name=${camp_site}]/site_type |
| `camp_id` | calculate |  |  | concat(${camp_site}, '-', format-date(today(), '%Y%m%d')) |
| `point_type` | select_one point_type | Where is this sample from? |  |  |
| `hh_method` | select_one id_method | Household ID: scan or type? |  |  |
| `hh_scan` | barcode | Scan the household sticker | ${hh_method}='scan' |  |
| `hh_type` | text | Type the household ID | ${hh_method}='type' |  |
| `hh_id` | calculate |  |  | if(${hh_method}='scan', ${hh_scan}, ${hh_type}) |
| `sample_id` | barcode | Scan the bottle label |  |  |
| `source` | select_one sample_src | Water source |  |  |
| `taken_at` | select_one sample_point | Taken from |  |  |
| `gps` | geopoint | Location of the source |  |  |
| `sampled_at` | calculate |  |  | now() |
| `tds` | integer | TDS (mg/L) |  |  |
| `water_temp` | decimal | Water temperature (°C) |  |  |
| `clarity` | select_one clarity | How does it look? |  |  |
| `smell` | select_one smell | Smell |  |  |
| `fu_colour` | integer | Forel-Ule colour (1–21), if a disk is used |  |  |
| `rain_48h` | select_one yes_no | Heavy rain in the past 48 hours? |  |  |
| `flooded_7d` | select_one yes_no | Source flooded in the past 7 days? |  |  |
| `aquadip` | select_one aq_result | Aquadip© result, if tested here |  |  |
| `aq_photo` | image | Photo of the Aquadip© result | ${aquadip}='pos' or ${aquadip}='neg' |  |
| `to_lab` | select_one yes_no | Sent to the NIO lab? |  |  |
| `notes` | text | Notes |  |  |
