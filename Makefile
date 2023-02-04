
# document (pdfs and xmls) directory
DIR    = ./data

# parsed json
DB_DIR = $(DIR)
DB_RAW = $(DB_DIR)/db.raw.json
DB     = $(DB_DIR)/db.json

# js, python, and makefile
SCRIPT_DIR = .
SCRIPT     = opa64.py

PYTHON3 = python3

all: $(DB)
db: $(DB)

$(DB_RAW): $(SCRIPT_DIR)/$(SCRIPT)
	$(PYTHON3) $(SCRIPT_DIR)/$(SCRIPT) fetch --doc=all --dir=$(DIR)
	$(PYTHON3) $(SCRIPT_DIR)/$(SCRIPT) parse --doc=all --dir=$(DIR) > $(DB_RAW)

$(DB): $(DB_RAW) 
	$(PYTHON3) $(SCRIPT_DIR)/$(SCRIPT) split --db=$(DB_RAW) > $(DB)

start:
	$(PYTHON3) -m http.server 8080 --directory=$(SCRIPT_DIR)

