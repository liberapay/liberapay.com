python := "$(shell { command -v python3.12 || command -v python3 || command -v python || echo false; } 2>/dev/null)"

# Set the relative path to installed binaries under the project virtualenv.
# NOTE: Creating a virtualenv on Windows places binaries in the 'Scripts' directory.
bin_dir := $(shell $(python) -c 'import sys; print("Scripts" if sys.platform == "win32" else "bin")')
env := env
env_bin := $(env)/$(bin_dir)
env_py := $(env_bin)/$(shell basename $(python))
pip := $(env_py) -m pip --disable-pip-version-check
with_local_env := $(env_py) cli/run.py -e defaults.env,local.env -s PYTHONPATH=.
with_tests_env := $(env_py) cli/run.py -e defaults.env,tests/test.env,tests/local.env -s PYTHONPATH=.
py_test := $(with_tests_env) $(env_py) -m pytest -Wd $$PYTEST_ARGS

echo:
	@echo $($(var))

$(env): Makefile requirements*.txt
	@if [ "$(python)" = "false" ]; then \
		echo "Unable to find a 'python' executable. Please make sure that Python is installed."; \
		exit 1; \
	fi;
	@$(python) cli/check-python-version.py
	$(python) -m venv --upgrade-deps $(env)
	$(pip) install wheel
	$(pip) install --require-hashes -r requirements_setup.txt
	$(pip) install --require-hashes -r requirements_base.txt
	$(pip) install -r requirements_tests.txt
	@touch $(env)

rehash-requirements:
	$(pip) install hashin
	f=requirements_base.txt; \
	sed -E -e '/^ *#/d' -e '/^ +--hash/d' -e 's/(; .+)?\\$$//' $$f | xargs $(env_bin)/hashin -r $$f;

clean:
	rm -rf $(env) *.egg *.egg-info
	find . -name \*.pyc -delete

schema: $(env)
	$(with_local_env) ./recreate-schema.sh

schema-diff: test-schema
	eb ssh liberapay -c 'pg_dump -sO' | sed -e '/^INFO: /d' >prod.sql
	$(with_tests_env) sh -c 'pg_dump -sO "$$DATABASE_URL"' >local.sql
	sed -E -e '/^--/d' -e '/^\s*$$/d' -e '/^SET /d' -e 's/\bpg_catalog\.//g' -i prod.sql local.sql
	diff -uw prod.sql local.sql
	rm prod.sql local.sql

data: $(env)
	$(with_local_env) $(env_py) -m liberapay.utils.fake_data

db-migrations: sql/migrations.sql
	$(with_local_env) $(env_py) liberapay/models/__init__.py

run: $(env)
	@$(MAKE) --no-print-directory db-migrations || true
	PATH=$(env_bin):$$PATH $(with_local_env) $(env_py) app.py

py: $(env)
	$(with_local_env) -s RUN_CRON_JOBS=no $(env_py) -i $${main-liberapay/main.py}

shell: py

test-shell: $(env)
	$(with_tests_env) $(env_py) -i $${main-liberapay/main.py}

test-schema: $(env)
	$(with_tests_env) ./recreate-schema.sh test

lint: $(env)
	$(env_py) -m ruff check app.py liberapay tests

test: test-schema pytest
tests: test

pytest: $(env)
	$(py_test) ./tests/py/test_$${PYTEST-*}.py
	@$(MAKE) --no-print-directory lint
	$(py_test) --doctest-modules liberapay

pytest-cov: $(env)
	$(py_test) --cov-report html --cov liberapay ./tests/py/test_$${PYTEST-*}.py
	@$(MAKE) --no-print-directory lint
	$(py_test) --doctest-modules liberapay

pytest-re: $(env)
	$(py_test) --lf ./tests/py/
	@$(MAKE) --no-print-directory lint

pytest-i18n-browse: $(env)
	@if [ -f sql/branch.sql ]; then $(MAKE) --no-print-directory test-schema; fi
	LIBERAPAY_I18N_TEST=yes $(py_test) -k TestTranslations ./tests/py/

pytest-profiling: $(env)
	LIBERAPAY_PROFILING=yes $(py_test) -k $${k-TestPerformance} --profile-svg ./tests/py/

update-test-deps: $(env)
	$(pip) install -U -r requirements_tests.txt

_i18n_extract: $(env)
	@PYTHONPATH=. $(env_bin)/pybabel extract -F .babel_extract --no-wrap -o i18n/core.pot --sort-by-file $$(\
		git ls-files | \
		grep -E '^(liberapay/.+\.py|.+\.(spt|html))$$' | \
		python -c "import sys; print(*sorted(sys.stdin, key=lambda l: l.rsplit('/', 1)))" \
	)
	@$(env_py) cli/po-tools.py reflag i18n/core.pot
	@for f in i18n/*/*.po; do \
		$(env_bin)/pybabel update -i i18n/core.pot -l $$(basename -s '.po' "$$f") -o "$$f" --ignore-obsolete --no-fuzzy-matching --no-wrap; \
	done
	rm i18n/core.pot

_i18n_clean: $(env)
	@for f in i18n/*/*.po; do \
	    echo "cleaning catalog $$f"; \
	    sed -E -e '/^"(POT?-[^-]+-Date|Last-Translator|X-Generator|Language|Project-Id-Version|Report-Msgid-Bugs-To): /d' \
	           -e 's/^("[^:]+: ) +/\1/' \
	           -e 's/^("Language-Team: .+? )<(.+)>\\n/\1"\n"<\2>\\n/' \
	           -e '/^#, python-format$$/d' \
	           -e 's/^#(, .+)?, python-format(, .+)?$$/#\1\2/' \
	           -e '/^#: /d' \
	           -e 's/\( (\{\w+_start\})/(\1/g' \
	           -e 's/_start\} /_start}/g' \
	           -e 's/ \{link_end\}/{link_end}/g' \
	           -e 's/\{link_end\} ([).,，。、])/{link_end}\1/g' \
	           "$$f" | \
	        $(env_py) -c "import sys; print(sys.stdin.read().rstrip())" > "$$f.new"; \
	    mv "$$f.new" "$$f"; \
	done

_i18n_convert: $(env)
	@$(env_py) cli/convert-chinese.py

i18n_update: _i18n_rebase _i18n_pull _i18n_extract _i18n_convert _i18n_clean
	@if git commit --dry-run i18n &>/dev/null; then \
		git commit -m "update translation catalogs" i18n; \
	fi
	@echo "Running i18n browse test..."
	@$(MAKE) --no-print-directory pytest-i18n-browse
	@echo "All done, check that everything is okay then push to master."

_i18n_rebase:
	@echo -n "Please go to https://hosted.weblate.org/projects/liberapay/#repository and click the Commit button if there are uncommitted changes, then press Enter to continue..."
	@read a

_i18n_fetch:
	@current_url=$$(git remote get-url weblate); \
	if [ "$$current_url" = "" ]; then \
	    git remote add weblate "https://hosted.weblate.org/git/liberapay/core/"; \
	elif [ "$$current_url" != "https://hosted.weblate.org/git/liberapay/core/" ]; then \
	    git remote set-url weblate "https://hosted.weblate.org/git/liberapay/core/"; \
	fi
	git fetch weblate

_i18n_pull: _i18n_fetch
	git checkout -q master
	@if git commit --dry-run i18n &>/dev/null; then \
		echo "There are uncommitted changes in the i18n/ directory." && exit 1; \
	fi
	@if test $$(git diff HEAD i18n | wc -c) -gt 0; then \
		echo "There are unstaged changes in the i18n/ directory." && exit 1; \
	fi
	git pull
	git merge -q --no-ff --no-commit -m "merge translations" weblate/master || true
	@if test $$(git diff HEAD i18n | wc -c) -gt 0; then \
		$(MAKE) --no-print-directory _i18n_merge; \
	fi

_i18n_merge:
	git reset -q master -- i18n
	@for f in i18n/*/*.po; do \
		if test $$(sed -E -e '/\\n"$$/{d;d}' $$f | grep -c -E '^"' 2>/dev/null) -gt 10; then \
			$(env_py) cli/po-tools.py reformat $$f; \
		fi \
	done
	@$(MAKE) --no-print-directory _i18n_clean
	@while true; do \
		git add -p i18n; \
		echo -n 'Are you done? (y/n) ' && read done; \
		test "$$done" = 'y' && break; \
	done
	git merge --continue
	git checkout -q HEAD -- i18n

bootstrap-upgrade:
	@if [ -z "$(version)" ]; then echo "You forgot the 'version=x.x.x' argument."; exit 1; fi
	wget https://github.com/twbs/bootstrap-sass/archive/v$(version).tar.gz -O bootstrap-sass-$(version).tar.gz
	tar -xaf bootstrap-sass-$(version).tar.gz
	rm -rf www/assets/bootstrap/{fonts,js}/*
	mv bootstrap-sass-$(version)/assets/javascripts/bootstrap.min.js www/assets/bootstrap/js
	mv bootstrap-sass-$(version)/assets/fonts/bootstrap/* www/assets/bootstrap/fonts
	rm -rf style/bootstrap
	mv bootstrap-sass-$(version)/assets/stylesheets/bootstrap style
	mv style/{bootstrap/_,}variables.scss
	git add style/bootstrap www/assets/bootstrap
	git commit -m "upgrade Bootstrap to $(version)"
	git commit -p style/variables.scss -m "merge upstream changes into variables.scss"
	git checkout -q HEAD style/variables.scss
	rm -rf bootstrap-sass-$(version){,.tar.gz}

stripe-bridge:
	$(with_local_env) $(env_py) cli/stripe-bridge.py
