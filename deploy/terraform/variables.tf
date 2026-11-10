variable "hcloud_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "create_servers" {
  type        = bool
  description = "Set true only when you intend to pay for VMs."
  default     = false
}

variable "server_count" {
  type    = number
  default = 1
}

variable "server_type" {
  type    = string
  default = "cpx21"
}

variable "location" {
  type    = string
  default = "fsn1"
}

variable "ssh_public_key" {
  type        = string
  description = "Contents of the public key, for example ssh-ed25519 AAAA..."
  default     = ""
}

variable "admin_cidrs" {
  type        = list(string)
  description = "Who may reach the Kubernetes API."
  default     = ["0.0.0.0/0"]
}

variable "cloudflare_api_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "cloudflare_account_id" {
  type    = string
  default = ""
}

variable "manage_dns" {
  type    = bool
  default = false
}

variable "cloudflare_zone_id" {
  type    = string
  default = ""
}

variable "dns_name" {
  type    = string
  default = "videomind"
}

variable "r2_bucket_name" {
  type    = string
  default = "videomind-videos"
}

variable "create_r2_bucket" {
  type    = bool
  default = false
}
