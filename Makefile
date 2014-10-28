python := "$(shell { command -v python2.7 || command -v python; } 2>/dev/null)"

# Set the relative path to installed binaries under the project virtualenv.
# NOTE: Creating a virtualenv on Windows places binaries in the 'Scripts' directory.
bin_dir := $(shell $(python) -c 'import sys; bin = "Scripts" if sys.platform == "win32" else "bin"; print(bin)')
env_bin := env/$(bin_dir)
venv := "./vendor/virtualenv-1.9.1.py"
test_env_files := defaults.env,tests/test.env,tests/local.env
pip := $(env_bin)/pip
honcho := $(env_bin)/honcho
honcho_run := $(honcho) -e defaults.env,local.env run
py_test := $(honcho) -e $(test_env_files) run $(env_bin)/py.test

env: requirements.txt requirements_tests.txt setup.py
	$(python) $(venv) \
				--unzip-setuptools \
				--prompt="[gratipay] " \
				--never-download \
				--extra-search-dir=./vendor/ \
				--distribute \
				./env/
	$(pip) install -r requirements.txt
	$(pip) install -r requirements_tests.txt
	$(pip) install -e ./

clean:
	rm -rf env *.egg *.egg-info
	find . -name \*.pyc -delete

schema: env
	$(honcho_run) ./recreate-schema.sh

data:
	$(honcho_run) $(env_bin)/fake_data fake_data

run: env
	PATH=$(env_bin):$(PATH) $(honcho_run) web

py: env
	$(honcho_run) $(env_bin)/python -i -c 'from gratipay.wireup import env, db; db = db(env())'

test-schema: env
	$(honcho) -e $(test_env_files) run ./recreate-schema.sh

pyflakes: env
	$(env_bin)/pyflakes bin gratipay tests

test: test-schema pytest jstest

pytest: env
	$(py_test) --cov gratipay ./tests/py/
	@$(MAKE) --no-print-directory pyflakes

retest: env
	$(py_test) ./tests/py/ --lf
	@$(MAKE) --no-print-directory pyflakes

test-cov: env
	$(py_test) --cov-report html --cov gratipay ./tests/py/

tests: test

node_modules: package.json
	npm install
	@if [ -d node_modules ]; then touch node_modules; fi

jstest: node_modules
	./node_modules/.bin/grunt test

transifexrc:
	@echo '[https://www.transifex.com]' >.transifexrc
	@echo 'hostname = https://www.transifex.com' >>.transifexrc
	@echo "password = $$TRANSIFEX_PASS" >>.transifexrc
	@echo 'token = ' >>.transifexrc
	@echo "username = $$TRANSIFEX_USER" >>.transifexrc

tx:
	@if [ ! -x $(env_bin)/tx ]; then $(env_bin)/pip install transifex-client; fi

i18n_upload: env tx
	$(env_bin)/pybabel extract -F .babel_extract --no-wrap -o i18n/core.pot templates www
	$(env_bin)/tx push -s
	rm i18n/*.pot

i18n_download: env tx
	$(env_bin)/tx pull -a -f --mode=reviewed --minimum-perc=50
	sed -e '/^"POT\?-[^-]\+-Date: /d' -i '' i18n/*/*.po
	sed -e '/^#: /d' -i '' i18n/*/*.po
