python := "$(shell { command -v python2.7 || command -v python; } 2>/dev/null)"
install_where := $(shell $(python) -c "import sys; print('' if hasattr(sys, 'real_prefix') else '--user')")

# Set the relative path to installed binaries under the project virtualenv.
# NOTE: Creating a virtualenv on Windows places binaries in the 'Scripts' directory.
bin_dir := $(shell $(python) -c 'import sys; print("Scripts" if sys.platform == "win32" else "bin")')
env_bin := env/$(bin_dir)
env_py := $(env_bin)/python
test_env_files := defaults.env,tests/test.env,tests/local.env
pip := pip --disable-pip-version-check
with_local_env := $(env_bin)/honcho run -e defaults.env,local.env
with_tests_env := $(env_bin)/honcho run -e $(test_env_files)

echo:
	@echo $($(var))

_warning:
	@echo -e "\nWarning: you're using an old version of python, you really should upgrade!\n"

env: requirements*.txt
	$(python) -m ensurepip $(install_where) || $(MAKE) --no-print-directory _warning
	$(python) -m $(pip) install $(install_where) "virtualenv>=15.0.0"
	$(python) -m virtualenv --no-download ./env/
	$(env_bin)/$(pip) install $$(for f in requirements*.txt; do echo "-r $$f"; done)
	@touch env

clean:
	rm -rf env *.egg *.egg-info
	find . -name \*.pyc -delete

schema: env
	$(with_local_env) ./recreate-schema.sh

schema-diff: test-schema
	rhc ssh $$APPNAME --command 'pg_dump -sO' >prod.sql
	$(with_tests_env) sh -c 'pg_dump -sO "$$DATABASE_URL"' >local.sql
	diff -uw prod.sql local.sql
	rm prod.sql local.sql

data: env
	$(with_local_env) $(env_py) -m liberapay.utils.fake_data

db-migrations: sql/migrations.sql
	PYTHONPATH=. $(with_local_env) $(env_py) liberapay/models/__init__.py

run: env db-migrations
	PATH=$(env_bin):$$PATH $(with_local_env) $(env_py) app.py

py: env
	PYTHONPATH=. $(with_local_env) $(env_py) -i liberapay/main.py

payday: env
	PYTHONPATH=. $(with_local_env) $(env_py) liberapay/billing/payday.py

test-schema: env
	$(with_tests_env) ./recreate-schema.sh test

pyflakes: env
	$(env_bin)/flake8 --select=F app.py liberapay tests

test: test-schema pytest
tests: test

_pytest:
	PYTHONPATH=. $(with_tests_env) sh -c '$(env_bin)/py.test -n $${PYTEST_SLAVES-2} $(args)'

pytest: env
	@$(MAKE) --no-print-directory _pytest args="./tests/py/test_$${PYTEST-*}.py"
	@$(MAKE) --no-print-directory pyflakes

pytest-cov: env
	@$(MAKE) --no-print-directory _pytest args="--cov-report html --cov liberapay ./tests/py/"

pytest-re: env
	@$(MAKE) --no-print-directory _pytest args="--lf ./tests/py/"
	@$(MAKE) --no-print-directory pyflakes

_i18n_extract: env
	@PYTHONPATH=. $(env_bin)/pybabel extract -F .babel_extract --no-wrap -o i18n/core.pot emails liberapay templates www
	@for f in i18n/*/*.po; do \
		$(env_bin)/pybabel update -i i18n/core.pot -l $$(basename -s '.po' "$$f") -o "$$f" --ignore-obsolete --no-fuzzy-matching --no-wrap; \
	done
	rm i18n/core.pot
	@$(MAKE) --no-print-directory _i18n_clean

_i18n_clean:
	@for f in i18n/*/*.po; do \
	    sed -E -e '/^"(POT?-[^-]+-Date|Last-Translator|X-Generator|Language): /d' \
	           -e 's/^("[^:]+: ) +/\1/' \
	           -e 's/^("Language-Team: .+? )<(.+)>\\n/\1"\n"<\2>\\n/' \
	           -e '/^#: /d' "$$f" >"$$f.new"; \
	    mv "$$f.new" "$$f"; \
	done

i18n_update: _i18n_rebase _i18n_pull _i18n_extract
	@if git commit --dry-run i18n &>/dev/null; then \
		git commit -m "update translation catalogs" i18n; \
	fi
	@echo "All done, check that everything is okay then push to master."

_i18n_rebase:
	@echo -n "Please go to https://hosted.weblate.org/update/liberapay/?method=rebase if you haven't done it yet, then press Enter to continue..."
	@read a

_i18n_fetch:
	@git remote | grep weblate >/dev/null || git remote add weblate git://git.weblate.org/liberapay.com.git
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
	git merge --squash weblate/master
	@if test $$(git diff HEAD i18n | wc -c) -gt 0; then \
		$(MAKE) --no-print-directory _i18n_merge; \
	fi

_i18n_merge:
	@git reset -q HEAD i18n
	@while true; do \
		git add -p i18n; \
		echo -n 'Are you done? (y/n) ' && read done; \
		test "$$done" = 'y' && break; \
	done
	@git diff --cached i18n >new-translations.patch
	@git checkout -q HEAD i18n
	@git merge -q --no-ff -m "merge translations" weblate/master
	@git checkout -q HEAD~ i18n
	@patch -s -p1 -i new-translations.patch
	@$(MAKE) --no-print-directory _i18n_clean
	@git add i18n
	@git commit --amend i18n
	rm new-translations.patch
