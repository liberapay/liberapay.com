# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  # We use multi-machine config here. First one to rebuild the box from scratch
  # (it is normally commented) and second (faster) that download built version. 

  # Previous configs are:
  # - https://github.com/gratipay/gratipay.com/blob/83312e60c6b31c298ffca61036baa9849044c75e/Vagrantfile
  # - https://github.com/gratipay/gratipay.com/blob/fc0b4395e85259cdd17d9fe8560bf654abd756ce/Vagrantfile


  # --- [ common access parameters ] ---

  # Gratipay app is accessible at http://localhost:8537/ from host
  #
  config.vm.network :forwarded_port, guest: 8537, host: 8537

  # Current folder is available as /vagrant from guest.
  # We speed up access by installing and using NFS as described here:
  # https://docs.vagrantup.com/v2/synced-folders/nfs.html
  config.vm.synced_folder ".", "/vagrant", type: "nfs"
  config.vm.network "private_network", ip: "172.27.36.119"


  # --- [ boxes ] ---
  #
  # after you bootstrap this box, saving it into a gratipay.box is as easy as
  # $ vagrant package --output gratipay.box
  #
  config.vm.define "basebox" do |base|
    # using Ubuntu 14.04, because it is what our hosting (Heroku) uses
    # (search cedar-14 for details)
    base.vm.box = "ubuntu/trusty64"

    # --- install prerequisites ---
    # [ ] use the same package versions as Heroku
    #   [ ] figure out how to fetch Heroku versions
    base.vm.provision "shell", inline: "sudo apt-get -y install postgresql"
  end

  # disable snapshot box for now
  #config.vm.define "gratipay" do |box|
  #  box.vm.box = "gratipay"
  #  box.vm.box_url =  File.exist?("gratipay.box") ? "file://gratipay.box" : "https://downloads.gratipay.com/gratipay.box"

  #  box.vm.provision :shell, :path => "scripts/vagrant-setup.sh"
  #end

end
