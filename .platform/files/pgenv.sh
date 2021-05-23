#!/bin/sh

export PGHOST=$(/opt/elasticbeanstalk/bin/get-config environment -k PGHOST)
export PGPORT=$(/opt/elasticbeanstalk/bin/get-config environment -k PGPORT)
export PGDATABASE=$(/opt/elasticbeanstalk/bin/get-config environment -k PGDATABASE)
export PGUSER=$(/opt/elasticbeanstalk/bin/get-config environment -k PGUSER)
export PGPASSWORD=$(/opt/elasticbeanstalk/bin/get-config environment -k PGPASSWORD)
