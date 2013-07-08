# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant::Config.run do |config|
    config.vm.box = "precise64"
    config.vm.box_url = "http://files.vagrantup.com/precise64.box"
    config.vm.forward_port 8537, 8537
    config.vm.customize([
        'setextradata',
        :id,
        'VBoxInternal2/SharedFoldersEnableSymlinksCreate/v-root',
        '1'
    ])

    config.vm.customize ["modifyvm", :id,
        "--natdnshostresolver1", "on",
        "--memory", "1024"]

    config.vm.provision :puppet do |puppet|
        puppet.module_path = "puppet/modules"
        puppet.manifests_path = "puppet/manifests"
        puppet.manifest_file  = "gittip.pp"
        puppet.facter = {"fqdn" => "precise64"}
    end

    config.vm.provision :shell, :inline => "echo DATABASE_URL='postgres://gittip:gittip@localhost:5432/gittip' >> /vagrant/local.env"
    config.vm.provision :shell, :inline => "cd /vagrant && make schema data"
    config.vm.provision :shell,
        :inline => 'echo "Provision complete!"; echo "To start the app, inside of \'vagrant ssh\', run \'cd /vagrant && make run\'"'
end
