FROM debian:8

RUN apt-get update && apt-get install build-essential wget libpq-dev python-dev postgresql-client libffi-dev libssl-dev -y

RUN wget -O /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py && python /tmp/get-pip.py

ADD ./requirements_base.txt /requirements/pip/base.txt
RUN pip install --require-hashes -r /requirements/pip/base.txt

ADD ./requirements_dev.txt /requirements/pip/dev.txt
RUN pip install --require-hashes -r /requirements/pip/dev.txt

ADD ./requirements_tests.txt /requirements/pip/tests.txt
RUN pip install --require-hashes -r /requirements/pip/tests.txt

ADD . /app
WORKDIR /app
