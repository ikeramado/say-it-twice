# Private keys: loaded from ENV_FILE when it exists; the environment or command line wins (?=).
# config/keys.example lists the two names without values: copy it to .env and fill it in.
ENV_FILE ?= .env
ifneq ($(wildcard $(ENV_FILE)),)
ANTHROPIC_API_KEY ?= $(shell sed -n 's/^ANTHROPIC_API_KEY=//p' $(ENV_FILE))
LLM_API_KEY ?= $(shell sed -n 's/^LLM_API_KEY=//p' $(ENV_FILE))
endif
export ANTHROPIC_API_KEY LLM_API_KEY

.PHONY: env-check
env-check:
	@test -n "$$ANTHROPIC_API_KEY" && echo "ANTHROPIC_API_KEY: set" || echo "ANTHROPIC_API_KEY: not set"
	@test -n "$$LLM_API_KEY" && echo "LLM_API_KEY: set" || echo "LLM_API_KEY: not set"

# The study agents `make dev-eval` runs (a comma inside $(or ...) would split its arguments).
STUDY_AGENTS ?= naive,cheap_strong,system
# Case-runs in flight at once (threads).
WORKERS ?= 16

.PHONY: check test lint

lint:
	uv run ruff check .

test:
	uv run pytest -q

check: lint test

.PHONY: ingest
ingest:
	@test -n "$(MONTH)" || { echo "usage: make ingest MONTH=YYYY-MM"; exit 2; }
	@uv run python -m ingest.pipeline $(MONTH)

.PHONY: ingest-t100
ingest-t100:
	@test -n "$(YEAR)" || { echo "usage: make ingest-t100 YEAR=YYYY"; exit 2; }
	@uv run python -m ingest.t100 $(YEAR)

.PHONY: estimate
estimate:
ifdef PROTOCOL
	@uv run python -m runner estimate --protocol $(PROTOCOL) $(if $(MODEL),--model $(MODEL))
else
	@uv run python -m runner estimate --agent $(or $(AGENT),placeholder) --cases $(or $(CASES),1) --runs $(or $(RUNS),1)
endif

.PHONY: smoke
smoke:
	@test -n "$(MODEL)" || { echo "usage: make smoke MODEL=<entry of config/models.yaml>"; exit 2; }
	@uv run python -m runner smoke --model $(MODEL)

.PHONY: skeleton
skeleton:
	@uv run python -m report.skeleton $(or $(MONTH),2024-07)

.PHONY: cases
cases:
	@uv run python -m cases.split

.PHONY: label-sheets label-import label-kappa label-rules label-freeze
label-sheets:
	@uv run python -m labeling sheets $(LABELER)
label-import:
	@uv run python -m labeling import $(LABELER)
label-kappa:
	@uv run python -m labeling kappa
label-rules:
	@uv run python -m labeler_rules
label-freeze:
	@uv run python -m labeling freeze

.PHONY: dev-subset dev-eval
dev-subset:
	@uv run python -m eval.subset

dev-eval:
	@test -n "$(BUDGET)" -a -n "$(CEILING)" || { echo "usage: make dev-eval BUDGET=<dollars per agent> CEILING=<dollars in all>"; exit 2; }
	@uv run python -m report.dev_eval --subset cases/dev/subset.txt --runs 3 --agents $(STUDY_AGENTS) --budget $(BUDGET) --ceiling $(CEILING) --workers $(WORKERS)

.PHONY: dev-full
# The full development run fixes the system's trigger window (prereg section 3): system only.
dev-full: STUDY_AGENTS = system
dev-full:
	@test -n "$(BUDGET)" -a -n "$(CEILING)" || { echo "usage: make dev-full BUDGET=<dollars per agent> CEILING=<dollars in all>"; exit 2; }
	@uv run python -m runner run --runs 10 --protocol dev-full --agents $(STUDY_AGENTS) --budget $(BUDGET) --ceiling $(CEILING) --workers $(WORKERS)

.PHONY: confirm confirm-exploratory
# Prereg section 3: the three agents on the test cases x 10, once, after the tag prereg-v1;
# the same command resumes a run cut by the network or the cost gate. It refuses (exit 2)
# without the tag, on a test hash that differs from the registered one, or once complete.
confirm:
	@test -n "$(BUDGET)" -a -n "$(CEILING)" || { echo "usage: make confirm BUDGET=<dollars per agent> CEILING=<dollars in all>"; exit 2; }
	@uv run python -m runner confirm --budget $(BUDGET) --ceiling $(CEILING) --workers $(WORKERS)

# Exploratory, after the confirmatory run: the naive agent with the `exploratory` model entry.
confirm-exploratory:
	@test -n "$(BUDGET)" -a -n "$(CEILING)" || { echo "usage: make confirm-exploratory BUDGET=<dollars> CEILING=<dollars in all>"; exit 2; }
	@uv run python -m runner confirm-exploratory --budget $(BUDGET) --ceiling $(CEILING) --workers $(WORKERS)

.PHONY: report-confirm reproduce
# The runs directory both read (prereg section 6; C12). ROOT_DIR: the tree of cases, rules and
# the frozen answers they read (the project by default; a test points both at a fixture).
RUNS_DIR ?= runs
ROOT_DIR ?= .
# The confirmatory report from runs/confirm-<agent>/ (no model call): exit 2 before the run is
# complete, 1 when an agent's run is incomplete or invalid (the report is still written).
report-confirm:
	@uv run python -m report.confirm --root $(ROOT_DIR) --runs-dir $(RUNS_DIR)

# Every report rebuilt from the cached runs; a provider that raises replaces the real one.
reproduce:
	@uv run python -m report.reproduce --root $(ROOT_DIR) --runs-dir $(RUNS_DIR)

# The static site (T46): site/index.html from runs/confirm/report.json and config/site.yaml.
.PHONY: site
site:
	@uv run python -m report.site --out site --runs-dir $(or $(RUNS_DIR),runs)

# The public copy (T66): `make publish DEST=<empty directory outside the repo>` writes a clean
# one-commit repository (config/public.yaml). It never pushes and adds no remote.
.PHONY: publish
publish:
	@test -n "$(DEST)" || { echo "usage: make publish DEST=<empty directory>" >&2; exit 2; }
	@uv run python -m publish --dest "$(DEST)"
