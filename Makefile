
DIR    = ./docs
DB_RAW = $(DIR)/db.raw.json
DB     = $(DIR)/db.json

SCRIPT_DIR = .
SCRIPT     = opa64.py

PYTHON3 = python3

$(DB_RAW):
	$(PYTHON3) $(SCRIPT_DIR)/$(SCRIPT) fetch --doc=all --dir=$(DIR)
	$(PYTHON3) $(SCRIPT_DIR)/$(SCRIPT) parse --doc=all --dir=$(DIR) > $(DB_RAW)

$(DB): $(DB_RAW) 
	$(PYTHON3) $(SCRIPT_DIR)/$(SCRIPT) relink --db=$(DB_RAW) > $(DB)

start: $(DB)
	$(PYTHON3) -m http.server 8080 --directory=$(SCRIPT_DIR)

