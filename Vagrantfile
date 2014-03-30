# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

PROJECT_DIRECTORY = 'www.gittip.com'

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.provider "virtualbox" do |v|
    v.customize ["modifyvm", :id, "--natdnshostresolver1", "on"]
  end

  config.vm.box = "precise64"
  config.vm.box_url = "http://files.vagrantup.com/precise64.box"

  # Sync the project directory and expose the app
  config.vm.synced_folder ".", "/home/vagrant/#{PROJECT_DIRECTORY}"
  config.vm.network :forwarded_port, guest: 8537, host: 8537

  # TODO: Pin apt-get packages to the same versions Heroku uses

  # Install dependencies
  config.vm.provision :shell, :inline => <<-eos
    echo 'deb http://apt.postgresql.org/pub/repos/apt/ precise-pgdg main' > /etc/apt/sources.list.d/postgresql.list
    wget -qO- https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
    echo 'deb http://ppa.launchpad.net/chris-lea/node.js/ubuntu precise main' > /etc/apt/sources.list.d/chrislea-nodejs.list
    wget -qO- 'http://keyserver.ubuntu.com:11371/pks/lookup?op=get&search=0xB9316A7BC7917B12' | apt-key add -
    apt-get update
    apt-get -y install make git build-essential python-software-properties postgresql-9.3 postgresql-contrib-9.3 libpq-dev python-dev nodejs
  eos

  # Configure Postgres
  config.vm.provision :shell, :inline => <<-eos
    sudo -u postgres psql -U postgres -qf /home/vagrant/#{PROJECT_DIRECTORY}/create_db.sql
    sudo -u postgres createuser --superuser root
    sudo -u postgres createuser --superuser vagrant
  eos

  # Warn if Windows newlines are detected and try to fix the problem
  config.vm.provision :shell, :inline => <<-eos
    cd #{PROJECT_DIRECTORY}

    if egrep -ql $'\r'\$ README.md; then
      echo
      echo '*** WARNING ***'
      echo 'CRLF detected. You must fix the line endings manually before continuing.'
      echo
      echo 'PROBLEM'
      echo 'Vagrant syncs your working directory with Ubuntu. Scripts and the Makefile'
      echo 'expect Unix line endings, but git converts them to Windows CRLF with autocrlf.'
      echo
      echo 'SOLUTION'
      echo '1. git stash               # Stash your work'
      echo '2. git rm --cached -r .    # Remove everything from the index'
      echo '3. git reset --hard        # Remove the index and working directory from git'
      echo
      echo 'Run "vagrant up" again afterward to continue.'
      echo '***************'

      echo
      echo 'Running "git config core.autocrlf false"'
      git config core.autocrlf false

      exit 1
    fi
  eos

  # Set up the environment, the database, and run Gittip
  config.vm.provision :shell, :inline => "cd #{PROJECT_DIRECTORY} && make env schema data"

  # add run script
  config.vm.provision :shell, :inline => <<-eos
    echo >> .profile
    echo '# Added for your convienience"' >> .profile
    echo "cd #{PROJECT_DIRECTORY}" >> .profile

    echo
    echo 'Gittip installed! To run,'
    echo '$ vagrant ssh'
    echo '$ make run'
  eos
end
