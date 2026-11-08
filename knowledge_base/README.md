# Legal knowledge base

Official Indian sources collected by `scripts/collect_sources.py` and indexed by `scripts/build_index.py`.
Every PDF must pass a content check before it counts as collected. `sources.json` holds the URL, date, hash and every failed attempt.

**20 of 28 sources indexed, 2,833 passages.** Search mode: hybrid (BM25 + embeddings).

RAG here means looking up passages at question time. No model has been trained on this material.

## Indexed

| Source | Jurisdiction | Status | Host |
|---|---|---|---|
| [Transfer of Property Act, 1882](https://www.indiacode.nic.in/bitstream/123456789/2338/1/A1882-04.pdf) | India (central) | in force | www.indiacode.nic.in |
| [Registration Act, 1908](https://www.indiacode.nic.in/bitstream/123456789/15937/1/the_registration_act%2C1908.pdf) | India (central) | in force (draft replacement Bill published 2025) | www.indiacode.nic.in |
| [Indian Stamp Act, 1899](https://revenue.py.gov.in/downloads/actsandrules/Indian%20StampAct1899.pdf) | India (central); states amend duty rates | in force | revenue.py.gov.in |
| [Real Estate (Regulation and Development) Act, 2016](https://www.up-rera.in/pdf/reraact.pdf) | India (central) | in force | www.up-rera.in |
| [Indian Contract Act, 1872](https://www.thc.nic.in/Central%20Governmental%20Acts/Indian%20Contract%20Act,%201872.pdf) | India (central) | in force | www.thc.nic.in |
| [Specific Relief Act, 1963](https://www.indiacode.nic.in/bitstream/123456789/1583/7/A1963-47.pdf) | India (central) | in force | www.indiacode.nic.in |
| [Limitation Act, 1963](https://www.thc.nic.in/Central%20Governmental%20Acts/Limitation%20Act,%202019.pdf) | India (central) | in force | www.thc.nic.in |
| [Hindu Succession Act, 1956](https://www.indiacode.nic.in/bitstream/123456789/1713/1/AAA1956suc___30.pdf) | India (central) | in force | www.indiacode.nic.in |
| [Indian Succession Act, 1925](https://www.thc.nic.in/Central%20Governmental%20Acts/Indian%20Succession%20Act,%201925.pdf) | India (central) | in force | www.thc.nic.in |
| [Powers of Attorney Act, 1882](https://indiacode.gov.in/server/api/core/bitstreams/e801bb57-6d01-41fc-a253-fed1f9c47f03/content) | India (central) | in force | indiacode.gov.in |
| [Indian Easements Act, 1882](https://www.thc.nic.in/Central%20Governmental%20Acts/Indian%20Easements%20Act,%201882.pdf) | India (central) | in force | www.thc.nic.in |
| [Partition Act, 1893](https://indiacode.gov.in/server/api/core/bitstreams/f98adb76-5420-4868-a1f9-e200011e3be2/content) | India (central) | in force | indiacode.gov.in |
| [Uttar Pradesh Revenue Code, 2006](https://www.lbsnaa.gov.in/storage/uploads/pdf_data/1742473203_Uttar%20Pradesh%20Revenue%20Code%202006%20updated%20till%2005.03.2021.pdf) | Uttar Pradesh | in force | www.lbsnaa.gov.in |
| [Maharashtra Land Revenue Code, 1966](https://indiacode.gov.in/server/api/core/bitstreams/de00ee10-97db-48e2-ba13-f25e652accad/content) | Maharashtra | in force | indiacode.gov.in |
| [Draft Registration Bill, 2025 (Department of Land Resources)](https://cdnbbsr.s3waas.gov.in/s3d69116f8b0140cdeb1f99a4d5096ffe4/uploads/2025/05/20250526906486876.pdf) | India (central) | DRAFT for consultation, not law. Enactment status not confirmed from an official source | cdnbbsr.s3waas.gov.in |
| [DILRMP Guidelines (Department of Land Resources, MoRD)](https://cdnbbsr.s3waas.gov.in/s3d69116f8b0140cdeb1f99a4d5096ffe4/uploads/2024/04/20240425160100930.pdf) | India (central) | government programme guidelines, not a statute | cdnbbsr.s3waas.gov.in |
| [Karam Singh v. Amarjit Singh, 2025 INSC 1238 (Supreme Court of India)](https://api.sci.gov.in/supremecourt/2022/32133/32133_2022_14_1502_65047_Judgement_15-Oct-2025.pdf) | India (central) | Supreme Court judgment | api.sci.gov.in |
| [Mansoor Saheb v. Salima, 2024 INSC 1006 (Supreme Court of India)](https://api.sci.gov.in/supremecourt/2006/12193/12193_2006_9_1506_58088_Judgement_19-Dec-2024.pdf) | India (central) | Supreme Court judgment | api.sci.gov.in |
| [P. Kishore Kumar v. Vittal K. Patkar, 2023 INSC 1009 (Supreme Court of India)](https://api.sci.gov.in/supremecourt/2011/10304/10304_2011_5_1501_48291_Judgement_20-Nov-2023.pdf) | India (central) | Supreme Court judgment | api.sci.gov.in |
| [MoHUA RERA portal](https://rera.mohua.gov.in/) | India (central) | government web page | rera.mohua.gov.in |

## Not available when collected

Their contents were not invented. Re-run the collector to try again.

| Source | Last recorded reason |
|---|---|
| Prohibition of Benami Property Transactions Act, 1988 | https://indiacode.gov.in/server/api/core/bitstreams/452acaca-88b8-408c-abb4-13160f555d15/content: rejected, only 2 pages, expected at least 15: probab |
| Karnataka Land Revenue Act, 1964 | https://indiacode.gov.in/server/api/core/bitstreams/cf46098e-9942-4e1d-bd79-8772ee2f96ad/content: rejected, only 1 pages, expected at least 40: probab |
| Model Tenancy Act, 2021 (MoHUA) | https://mohua.gov.in/upload/uploadfiles/files/Model-Tenancy-Act-English-02_06_2021.pdf: HTTP 404 |
| Uttarakhand Tenancy Act, 2021 (state enactment based on the Model Tenancy Act) | https://www.indiacode.nic.in/bitstream/123456789/20015/1/uk_tenancy_act,_2021_eng.pdf: HTTP 504 |
| Department of Land Resources: website | https://www.dolr.gov.in/: page has too little server-rendered text (0 chars) |
| Department of Land Resources: Digital India Land Records Modernization Programme | https://dolr.gov.in/en/programme-schemes/dilrmp/digital-india-land-records-modernization-programme: HTTP 404 |
| IGRS Uttar Pradesh (registration department portal) | https://igrsup.gov.in/: page has too little server-rendered text (0 chars) |
| UP Bhulekh (land records portal) | https://upbhulekh.gov.in/: page has too little server-rendered text (5 chars) |

## How current these texts are

Texts are as published on the hosting site when collected. They were not compared line by line against the latest amendments, and no lawyer has reviewed them.

- **Indian Stamp Act:** the copy says it is as amended by the Finance Act, 2006, and comes from Puducherry's revenue site. Stamp duty is largely set by states, so check state law for rates.
- **Uttar Pradesh Revenue Code:** this copy is updated to 5 March 2021.
- **Indian Succession Act:** this copy says it is modified to 26 November 2018.
- **Limitation Act, Contract Act, Succession Act, Easements Act:** India Code's old server returned errors, so copies came from a High Court website (thc.nic.in). The file behind the Limitation Act has "2019" in its name, but its content is the 1963 Act.
- **Draft Registration Bill, 2025:** a draft for consultation, so it is left out of search unless a question asks about it. Whether it has been enacted was not confirmed from an official source. If it has, Registration Act answers may be out of date.
- **Supreme Court judgments:** the passages on mutation were read in the PDFs: Karam Singh (p.11), Mansoor Saheb (p.20), P. Kishore Kumar (p.10).
- **State coverage:** only Uttar Pradesh and Maharashtra revenue law is indexed. Karnataka's Act could not be collected.

State portals that render in the browser (IGRS UP, UP Bhulekh, DoLR home page) return no readable text to a script. No CAPTCHA, login or site protection was bypassed.
