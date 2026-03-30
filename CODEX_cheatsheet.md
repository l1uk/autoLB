Certo — qui sotto ti lascio una **cheat sheet operativa** in italiano, pensata proprio per il tuo progetto:

**Word spec → normalized requirements → analisi legacy PyQt → target architecture → sviluppo webapp → aggiornamenti dello spec**

Codex CLI gira localmente nella directory selezionata, può leggere/modificare/eseguire codice nel progetto, e usa config sia globale (`~/.codex/config.toml`) sia di progetto (`.codex/config.toml`). Riconosce anche istruzioni di progetto come `AGENTS.md` risalendo dalla working directory fino alla root del progetto. ([OpenAI Developers][1])

## 1. Struttura minima del progetto

```text
migration-workspace/
├── legacy-app/
├── webapp/
├── docs/
│   ├── spec/
│   │   ├── extracted.md
│   │   ├── normalized-requirements.md
│   │   └── changes/
│   └── architecture/
├── .codex/
│   └── config.toml
└── AGENTS.md
```

## 2. File da avere sempre

### `.codex/config.toml`

Codex supporta config globale e project-scoped; i flag da CLI possono sovrascrivere i valori della config solo per quella singola esecuzione. ([OpenAI Developers][2])

Esempio minimale:

```toml
model = "gpt-5.4"
```

### `AGENTS.md`

Codex usa `AGENTS.md` come istruzioni persistenti di progetto; puoi anche definire nomi alternativi via config, ma `AGENTS.md` è il caso standard. ([OpenAI Developers][3])

Esempio:

```md
# AGENTS.md

This project migrates a legacy Python Qt desktop application into a web application.

Rules:
- Work in phases: discovery, validation, execution.
- Do not invent requirements.
- Treat normalized-requirements.md as source of truth.
- Keep requirement IDs stable.
- Prefer small, reviewable changes.
- Separate confirmed behavior, inferred behavior, and open questions.
```

---

# CHEAT SHEET OPERATIVA

## A. Avvio di Codex

Apri il terminale nella root del progetto:

```bash
cd ~/Documents/migration-workspace
npx @openai/codex
```

Se il progetto ha bisogno di accesso pieno al workspace locale, puoi usare il flag di approvazione ampia; la CLI documenta opzioni e override da riga di comando nella reference ufficiale. ([OpenAI Developers][4])

## B. Reset rapido della sessione

Per ripartire da zero con il contesto della chat ma senza toccare i file:

```text
/new
```

## C. Regola base

**Non chiedere mai a Codex di “riscrivere tutto” all’inizio.**
Usa sempre questo ordine:

1. discovery
2. validazione
3. scrittura documenti
4. architettura target
5. implementazione per feature

---

# 3. Fase SPEC

## Obiettivo

Trasformare il Word in `normalized-requirements.md`.

## Input

* `docs/spec/extracted.md`

## Output

* `docs/spec/normalized-requirements.md`

## Prompt standard

```text
You are a senior product analyst.

Your task is to transform the content of a raw specification document into a structured, implementation-ready functional requirements document.

Input:
- ./docs/spec/extracted.md

Output:
- ./docs/spec/normalized-requirements.md

Instructions:
- Do NOT copy the text verbatim.
- Clean, restructure, and normalize all information.
- Remove ambiguity, redundancy, and vague wording.
- Infer structure when missing, but do not invent features.
- Every requirement must be testable.
- If something is unclear, place it in Open Questions.

Structure:
1. Overview
2. Users
3. Core Workflows
4. Functional Requirements
5. Business Rules
6. Data Model (Conceptual)
7. Non-Functional Requirements
8. Out of Scope
9. Open Questions
```

## Regola decisionale importante

Se Codex ti fa domande su punti poco chiari, rispondi così:

* **se è confermato dallo spec o dal codice** → includilo
* **se appare solo in UI o in modo ambiguo** → mettilo in `Open Questions`
* **se esiste nel legacy ma non nello spec** → segnalo come “legacy-only capability”, non come requirement confermato

---

# 4. Fase ANALISI LEGACY

## Obiettivo

Capire la codebase PyQt senza ancora migrare nulla.

## Output attesi

* `docs/architecture/legacy-analysis.md`
* `docs/spec/feature-mapping.md`
* `docs/architecture/migration-risks.md`

## Prompt standard

```text
You are analyzing a legacy Python desktop application and comparing it against the functional requirements.

Inputs:
- ./legacy-app
- ./docs/spec/normalized-requirements.md

Your task is to perform reverse engineering of the legacy codebase.

Phase 1: discovery only
- Inspect the project structure
- Identify entry points
- Identify major modules and packages
- Detect UI-specific code (Qt/PyQt/PySide classes, windows, dialogs, widgets)
- Detect business logic, services, models, repositories, utility layers, and file I/O
- Detect configuration files, database access, external integrations, background tasks, and exports/imports
- Identify obvious dead code or obsolete modules if visible

Rules:
- Do NOT modify code
- Do NOT migrate anything yet
- Be conservative
- If uncertain, explicitly mark uncertainty

Outputs:
1. ./docs/architecture/legacy-analysis.md
2. ./docs/spec/feature-mapping.md
3. ./docs/architecture/migration-risks.md

Before writing files:
- first print a short analysis plan
- list the most relevant files/directories
```

## Cosa deve trovare

* entry points
* classi Qt/UI
* servizi e logica business
* persistenza dati
* import/export
* coupling forte tra UI e dominio
* feature legacy mappate agli ID dei requirements

## Red flags da segnare

* logica business dentro widget Qt
* SQL/file I/O dentro finestre o dialog
* validazioni disperse nella UI
* config/import/export poco specificati
* feature legacy non presenti nello spec

---

# 5. Fase TARGET ARCHITECTURE

## Obiettivo

Definire come la webapp dovrà essere costruita.

## Prompt standard

```text
Using:
- ./docs/spec/normalized-requirements.md
- ./docs/spec/feature-mapping.md
- ./docs/architecture/legacy-analysis.md
- ./docs/architecture/migration-risks.md

Design a migration architecture from the legacy Python Qt desktop app to a modern web application.

Goals:
- preserve business-critical behavior
- support incremental migration
- reduce coupling
- remain maintainable

Create:
- ./docs/architecture/target-architecture.md
- ./docs/architecture/migration-plan.md

Include:
- recommended frontend
- recommended backend
- data persistence approach
- API boundaries
- authentication approach
- migration phases
- first slice to implement
```

## Regola pratica

Per un’app legacy Python/Qt, in genere conviene:

* backend Python
* frontend web separato
* migrazione feature-by-feature

---

# 6. Fase SVILUPPO

## Metodo giusto

**Una feature verticale alla volta.**

Ordine:

1. requirement
2. comportamento legacy
3. API
4. UI
5. test
6. note di migrazione

## Prompt per implementare una feature

```text
Implement feature FR-00X from ./docs/spec/normalized-requirements.md.

Before coding:
- inspect how this feature works in ./legacy-app
- summarize current legacy behavior
- list assumptions

Then implement:
- backend support
- frontend UI
- minimal tests
- migration notes

Rules:
- preserve confirmed business rules
- do not invent behavior
- keep the change small and reviewable
```

## Prompt per refactor locale

```text
Refactor this area without changing behavior.

Goals:
- separate UI concerns from business logic
- reduce coupling
- improve readability
- keep behavior unchanged

Before editing:
- explain the current structure
- explain the proposed refactor
```

---

# 7. Fase TEST / VALIDAZIONE

## Prompt per controllo allineamento spec vs codice

```text
Check whether the current implementation matches ./docs/spec/normalized-requirements.md.

List:
- implemented requirements
- partially implemented requirements
- missing requirements
- inconsistent behavior
- risky assumptions in code
```

## Prompt per regressione

```text
Review the latest changes for regression risk.

Focus on:
- business rules
- data persistence
- imports/exports
- validation
- permissions
```

---

# 8. AGGIORNAMENTO DELLO SPEC

## Regola d’oro

**Mai sovrascrivere lo spec senza versionarlo.**

Usa qualcosa del genere:

```text
docs/spec/
├── normalized-requirements-v1.md
├── normalized-requirements-v2.md
└── changes/
    └── v2-changelog.md
```

## Workflow corretto

1. arriva nuovo Word
2. converti in `extracted-v2.md`
3. confronti con `normalized-requirements-v1.md`
4. produci changelog
5. aggiorni lo spec in `v2`
6. verifichi impatto sul codice

## Prompt per diff di spec

```text
Compare:
- ./docs/spec/normalized-requirements-v1.md
- ./docs/spec/extracted-v2.md

Identify only the differences.

Classify them as:
- new features
- modified features
- removed features
- clarified business rules
- unresolved ambiguities

Write:
- ./docs/spec/changes/v2-changelog.md
```

## Prompt per aggiornare lo spec

```text
Apply the changes from ./docs/spec/changes/v2-changelog.md to ./docs/spec/normalized-requirements-v1.md.

Rules:
- keep existing IDs when possible
- add new IDs only for genuinely new requirements
- mark deprecated items instead of silently deleting them

Output:
- ./docs/spec/normalized-requirements-v2.md
```

## Prompt per impatto sul codice

```text
Check the current codebase against ./docs/spec/normalized-requirements-v2.md.

List:
- code already compliant
- code needing updates
- requirements not yet implemented
- risky mismatches
```

---

# 9. COME RISPONDERE ALLE DOMANDE DI CODEX

## Quando Codex chiede chiarimenti su requisiti ambigui

Usa questa logica:

### Risposta tipo 1 — conservativa

```text
If it is not clearly confirmed by the source spec or legacy behavior, do not normalize it as a confirmed requirement.
Document it under Open Questions.
```

### Risposta tipo 2 — legacy-only

```text
Include it as observed legacy functionality, but do not treat it as a confirmed in-scope requirement unless the spec explicitly confirms it.
```

### Risposta tipo 3 — UI note only

```text
If the behavior appears only in the UI and backend/domain behavior is not clear, treat it as a UI note and not as a confirmed functional requirement.
```

### Risposta tipo 4 — implementation note, not requirement

```text
You may mention it as a possible implementation approach, but not as a confirmed requirement.
```

---

# 10. PROMPT UTILI PRONTI

## A. Discovery only

```text
Start with discovery only.
Do not write code yet.
First:
- inventory the project
- identify entry points
- identify module boundaries
- identify legacy feature clusters
```

## B. Plan before action

```text
Before making changes:
- summarize your understanding
- identify risks
- propose a small implementation plan
- wait for execution within the same task
```

## C. Conservative mode

```text
Be conservative.
Separate:
- confirmed behavior
- inferred behavior
- open questions
Do not upgrade inferred behavior into confirmed requirements.
```

## D. Review changes

```text
Review all files changed in this task.
Summarize:
- what changed
- why
- risks
- follow-up work
```

---

# 11. COSE DA NON FARE

## Non fare

* “rewrite the whole app as a webapp”
* “generate the full backend and frontend now”
* “assume missing requirements”
* “delete old behavior without mapping it”

## Fai invece

* discovery
* mapping
* architecture
* one feature at a time
* validation after each step

---

# 12. ROUTINE CONSIGLIATA DI LAVORO

## Quando inizi una nuova sessione

1. apri Codex nella root del progetto
2. controlla che veda i file giusti
3. ricordagli la source of truth
4. dagli un task piccolo

Prompt breve:

```text
Use ./docs/spec/normalized-requirements.md as source of truth.
Work in phases: discovery, validation, execution.
Keep changes small and reviewable.
```

## Quando finisci una sessione

Chiedi sempre:

```text
Summarize:
- files changed
- requirements affected
- assumptions made
- remaining risks
- recommended next step
```

---

# 13. CHECKLIST FINALE

## Prima di sviluppare

* [ ] normalized requirements pronti
* [ ] legacy analysis pronta
* [ ] feature mapping pronto
* [ ] migration risks pronti
* [ ] target architecture pronta
* [ ] first slice definita

## Durante lo sviluppo

* [ ] una feature per volta
* [ ] requirements ID citati
* [ ] comportamento legacy verificato
* [ ] test minimi aggiunti
* [ ] note di migrazione aggiornate

## Quando cambia lo spec

* [ ] nuova versione
* [ ] changelog
* [ ] impatto sul codice
* [ ] aggiornamento incrementale

---

# 14. Nota finale pratica

Codex supporta anche MCP servers, config condivisa tra CLI e IDE, e persino custom subagents definiti in `~/.codex/agents/` o `.codex/agents/` per ruoli specifici come explorer o worker; questo può tornarti utile più avanti se vuoi separare analisi, implementazione e review in flussi più strutturati. ([OpenAI Developers][5])

Se vuoi, nel messaggio dopo posso trasformare questa cheat sheet in una **versione markdown già pulita e pronta da copiare nel tuo file `CODEX_CHEATSHEET.md`**.

[1]: https://developers.openai.com/codex/cli/?utm_source=chatgpt.com "Codex CLI"
[2]: https://developers.openai.com/codex/config-basic/?utm_source=chatgpt.com "Config basics – Codex"
[3]: https://developers.openai.com/codex/guides/agents-md/?utm_source=chatgpt.com "Custom instructions with AGENTS.md – Codex"
[4]: https://developers.openai.com/codex/cli/reference/?utm_source=chatgpt.com "Codex CLI - Command line options"
[5]: https://developers.openai.com/codex/mcp/?utm_source=chatgpt.com "Model Context Protocol – Codex"
