require "json"

config_path = File.join(__dir__, ".cluster", "config.json")
unless File.file?(config_path)
  abort "Gere a topologia primeiro: python -m scripts.cluster.preparar"
end
cluster = JSON.parse(File.read(config_path))

Vagrant.configure("2") do |config|
  config.vm.box = cluster.fetch("box")
  config.vm.box_version = cluster.fetch("box_version")
  config.vm.boot_timeout = 600
  # Não exponha .vagrant/ (chaves de gerenciamento), .venv/ ou .tools/ aos nós.
  config.vm.synced_folder ".", "/vagrant", disabled: true
  %w[infra src scripts tests .cluster dados].each do |path|
    if File.directory?(File.join(__dir__, path))
      config.vm.synced_folder path, "/vagrant/#{path}",
        mount_options: ["ro", "dmode=755", "fmode=644"]
    end
  end

  cluster.fetch("cluster_nodes").each do |node|
    config.vm.define node.fetch("name") do |machine|
      machine.vm.hostname = node.fetch("name")
      machine.vm.network "private_network", ip: node.fetch("ip"), netmask: "255.255.255.0"
      machine.vm.provider "virtualbox" do |vb|
        vb.name = "projeto-sd-#{node.fetch('name')}"
        vb.cpus = cluster.fetch("cpus")
        vb.memory = cluster.fetch("memory_mb")
        vb.gui = false
      end

      machine.vm.provision "shell", path: "infra/bootstrap.sh"
      machine.vm.provision "ansible_local" do |ansible|
        ansible.install = false
        ansible.provisioning_path = "/vagrant"
        ansible.playbook = "infra/ansible/node.yml"
        ansible.inventory_path = ".cluster/inventory-local/#{node.fetch('name')}.ini"
        ansible.extra_vars = cluster
      end
    end
  end
end
