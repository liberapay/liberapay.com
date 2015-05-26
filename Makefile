python := "$(shell { command -v python2.7 || command -v python; } 2>/dev/null)"

# Set the relative path to installed binaries under the project virtualenv.
# NOTE: Creating a virtualenv on Windows places binaries in the 'Scripts' directory.
bin_dir := $(shell $(python) -c 'import sys; print("Scripts" if sys.platform == "win32" else "bin")')
env_bin := env/$(bin_dir)
test_env_files := defaults.env,tests/test.env,tests/local.env
pip := $(env_bin)/pip --disable-pip-version-check
with_local_env := $(env_bin)/honcho run -e defaults.env,local.env
with_tests_env := $(env_bin)/honcho run -e $(test_env_files)
py_test := $(with_tests_env) $(env_bin)/py.test

ifdef PYTEST
	pytest = ./tests/py/$(PYTEST)
else
	pytest = ./tests/py/
endif

env: requirements.txt requirements_tests.txt
	$(python) -m virtualenv ./env/
	$(pip) install -r requirements.txt
	$(pip) install -r requirements_tests.txt
	@touch env

clean:
	rm -rf env *.egg *.egg-info
	find . -name \*.pyc -delete

schema: env
	$(with_local_env) ./recreate-schema.sh

schema-diff: test-schema
	pg_dump -sO `heroku config:get DATABASE_URL -a liberapay` >prod.sql
	$(with_tests_env) sh -c 'pg_dump -sO "$$DATABASE_URL"' >local.sql
	diff -uw prod.sql local.sql
	rm prod.sql local.sql

data: env
	$(with_local_env) $(env_bin)/python -m liberapay.utils.fake_data

run: env
	$(with_local_env) make --no-print-directory run_

run_:
	$(env_bin)/$(shell grep -E '^web: ' Procfile | cut -d' ' -f2-)

py: env
	$(with_local_env) $(env_bin)/python -i liberapay/main.py

test-schema: env
	$(with_tests_env) ./recreate-schema.sh test

pyflakes: env
	$(env_bin)/pyflakes liberapay tests

test: test-schema pytest
tests: test

pytest: env
	PYTHONPATH=. $(py_test) --cov liberapay $(pytest)
	@$(MAKE) --no-print-directory pyflakes

pytest-cov: env
	PYTHONPATH=. $(py_test) --cov-report html --cov liberapay ./tests/py/

pytest-re: env
	PYTHONPATH=. $(py_test) --lf ./tests/py/
	@$(MAKE) --no-print-directory pyflakes

i18n: env
	$(env_bin)/pybabel extract -F .babel_extract --no-wrap -o i18n/core.pot emails liberapay templates www

i18n_upload: i18n
	$(env_bin)/tx push -s
	rm i18n/*.pot

i18n_download: env
	$(env_bin)/tx pull -a -f --mode=reviewed --minimum-perc=50
	@for f in i18n/*/*.po; do \
	    sed -E -e '/^"POT?-[^-]+-Date: /d' \
	           -e '/^"Last-Translator: /d' \
	           -e '/^#: /d' "$$f" >"$$f.new"; \
	    mv "$$f.new" "$$f"; \
	done
