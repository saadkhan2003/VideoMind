output "node_ipv4" {
  value       = hcloud_server.node[*].ipv4_address
  description = "Public IPv4 addresses of the k3s nodes. Empty until create_servers is true."
}

output "r2_bucket" {
  value       = one(cloudflare_r2_bucket.videos[*].name)
  description = "R2 bucket name, if create_r2_bucket is true."
}

output "dns_name" {
  value = var.manage_dns ? var.dns_name : ""
}
