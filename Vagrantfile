# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.provider "virtualbox" do |v|
    v.customize ["modifyvm", :id, "--natdnshostresolver1", "on"]
  end

  # For now we have a custom built vagrant image. It was built in the following manner:
  #
  #  - Use 'precise64' as a base.
  #  - perform a 'vagrant up' using this vagrantfile: 
  #     https://github.com/gratipay/gratipay.com/blob/83312e60c6b31c298ffca61036baa9849044c75e/Vagrantfile
  #  - drop database gratipay
  #  - drop role gratipay
  #
  # Here are some instructions for modifying an existing box:
  #
  #   http://www.pvcloudsystems.com/2012/10/vagrant-modify-existing-box/
  #
  # I used that successfully on https://github.com/gratipay/gratipay.com/pull/2815.

  config.vm.box = "gratipay"
  config.vm.box_url =  File.exist?("gratipay.box") ? "file://gratipay.box" : "https://downloads.gratipay.com/gratipay.box"

  # Sync the project directory and expose the app
  config.vm.network "private_network", ip: "172.27.36.119"
  config.vm.synced_folder ".", "/vagrant", type: "nfs"
  config.vm.network :forwarded_port, guest: 8537, host: 8537

  # TODO: Pin apt-get packages to the same versions Heroku uses

  # Installed dependencies are already part of the base image now
  config.vm.provision :shell,
    :path => "scripts/vagrant-setup.sh"
end
