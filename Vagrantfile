# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

PROJECT_DIRECTORY = 'www.gittip.com'

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.provider "virtualbox" do |v|
    v.customize ["modifyvm", :id, "--natdnshostresolver1", "on"]
  end

  #For now we have a custom built vagrant image. It was built in the following manner:
  #-Use 'precise64' as a base.
  #-perform a 'vagrant up' using this vagrantfile: https://github.com/gittip/www.gittip.com/blob/83312e60c6b31c298ffca61036baa9849044c75e/Vagrantfile
  #-drop database gittip
  #-drop role gittip
  config.vm.box = "gittip"
  config.vm.box_url =  File.exist?("gittip.box") ? "file://gittip.box" : "http://downloads.gittipllc.netdna-cdn.com/gittip.box"

  # Sync the project directory and expose the app
  config.vm.synced_folder ".", "/home/vagrant/#{PROJECT_DIRECTORY}"
  config.vm.network :forwarded_port, guest: 8537, host: 8537

  # TODO: Pin apt-get packages to the same versions Heroku uses

  # Installed dependencies are already part of the base image now

  # Configure Postgres
  config.vm.provision :shell, :inline => <<-eos
    sudo -u postgres psql -U postgres -qf /home/vagrant/#{PROJECT_DIRECTORY}/create_db.sql
    # Root  and vagrant users are now part of the base image
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
  config.vm.provision :shell, :inline => "cd #{PROJECT_DIRECTORY} && make clean env schema data"

  # add run script
  config.vm.provision :shell, :inline => <<-eos
    echo >> .profile
    echo '# Added for your convienience"' >> .profile
    echo "cd /home/vagrant/#{PROJECT_DIRECTORY}" >> .profile

    echo
    echo 'Gittip installed! To run,'
    echo '$ vagrant ssh'
    echo '$ make run'
  eos
end
