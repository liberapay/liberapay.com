# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant::Config.run do |config|
    config.vm.box = "precise64"
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
end
