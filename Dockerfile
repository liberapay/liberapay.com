FROM debian:8

RUN apt-get update && apt-get install build-essential wget libpq-dev python-dev postgresql-client -y

RUN wget -O /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py && python /tmp/get-pip.py

ADD ./requirements.txt /requirements/pip/base.txt
RUN pip install -r /requirements/pip/base.txt

ADD ./requirements_dev.txt /requirements/pip/dev.txt
RUN pip install -r /requirements/pip/dev.txt

ADD ./requirements_tests.txt /requirements/pip/tests.txt
RUN pip install -r /requirements/pip/tests.txt

ADD . /app
WORKDIR /app
