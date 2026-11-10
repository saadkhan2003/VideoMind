provider "hcloud" {
  token = var.hcloud_token
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

resource "hcloud_ssh_key" "admin" {
  count      = var.create_servers && var.ssh_public_key != "" ? 1 : 0
  name       = "videomind-admin"
  public_key = var.ssh_public_key
}

resource "hcloud_firewall" "videomind" {
  count = var.create_servers ? 1 : 0
  name  = "videomind"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = var.admin_cidrs
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "6443"
    source_ips = var.admin_cidrs
  }
}

resource "hcloud_server" "node" {
  count       = var.create_servers ? var.server_count : 0
  name        = "videomind-${count.index}"
  server_type = var.server_type
  image       = "ubuntu-24.04"
  location    = var.location
  ssh_keys    = hcloud_ssh_key.admin[*].id
  firewall_ids = hcloud_firewall.videomind[*].id
  user_data   = file("${path.module}/../k8s/cloud-init.yaml")

  labels = {
    project = "videomind"
    role    = count.index == 0 ? "server" : "agent"
  }
}

resource "cloudflare_record" "app" {
  count   = var.manage_dns && var.create_servers ? 1 : 0
  zone_id = var.cloudflare_zone_id
  name    = var.dns_name
  type    = "A"
  content = hcloud_server.node[0].ipv4_address
  proxied = false
  ttl     = 300
}

resource "cloudflare_r2_bucket" "videos" {
  count      = var.create_r2_bucket ? 1 : 0
  account_id = var.cloudflare_account_id
  name       = var.r2_bucket_name
  location   = "WEUR"
}
