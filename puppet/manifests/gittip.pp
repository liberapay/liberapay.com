# install postgres
# custom pg_hba.conf
# create gittip user in postgres

group { 'puppet':
    ensure => 'present',
}

class { 'postgres': }

class dbschema {
  Exec { require => Class[postgres] }
}


Exec { path => '/usr/bin:/bin:/usr/sbin:/sbin' }

class postgres {
    Package {require => Ppa['pitti/postgresql']}

    package {
      'postgresql-9.2':
        ensure => present,
        ;
      'postgresql-contrib-9.2':
        ensure => present,
        ;
      'postgresql-server-dev-9.2':
        ensure => present,
        ;
    }

    file {
      'pg_hba.conf':
        ensure  => file,
        path    => '/etc/postgresql/9.2/main/pg_hba.conf',
        require => Package['postgresql-9.2'],
        source  => 'puppet:///modules/postgres/pg_hba.conf';
      'add_gittip_user.sql':
        ensure  => file,
        path    => '/tmp/add_gittip_user.sql',
        require => [Package['postgresql-9.2'], Exec[pgrestart]],
        source  => 'puppet:///modules/postgres/add_gittip_user.sql';
      'add_gittip_db.sh':
        ensure  => file,
        path    => '/tmp/add_gittip_db.sh',
        require => [
          Package['postgresql-9.2'],
          Package['postgresql-contrib-9.2'],
          Package['postgresql-server-dev-9.2'],
          Exec[pgrestart],
          Exec[makeuser]
        ],
        source  => 'puppet:///modules/postgres/add_gittip_db.sh';
    }

    exec {
      'pgrestart':
        command => '/etc/init.d/postgresql restart',
        require => File['pg_hba.conf'];
      'makeuser':
        command => 'psql -U postgres -f /tmp/add_gittip_user.sql',
        require => File['add_gittip_user.sql'];
      'makedb':
        command => '/tmp/add_gittip_db.sh',
        require => File['add_gittip_db.sh'];
    }

    ppa {
      'pitti/postgresql':;
    }
}

exec {
  'aptupdate':
    command => 'apt-get update';
}

package {
    'make':
      ensure  => present,
      require => Exec[aptupdate];
    'python-software-properties':
      ensure  => present,
      require => Exec[aptupdate];
    'python-dev':
      ensure  => present,
      require => Exec[aptupdate];
}

define ppa($ppa = "${title}", $ensure = present) {

  case $ensure {
    present: {
        $stupid_escapes = '\1-\2'
        $filename = regsubst($ppa, '(^.*)/(.*$)', "${stupid_escapes}-${::lsbdistcodename}.list")

        exec { $ppa:
            command => "add-apt-repository ppa:${ppa};apt-get update",
            require => Package['python-software-properties'],
            unless  => "test -e /etc/apt/sources.list.d/${filename}";
        }
    }

    absent:  {
        package {
            'ppa-purge': ensure => present;
        }

        exec { $ppa:
            command => "ppa-purge ppa:${ppa};apt-get update",
            require => Package[ppa-purge];
        }
    }

    default: {
      fail "Invalid 'ensure' value '${ensure}' for ppa"
    }
  }
}

