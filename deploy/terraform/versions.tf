terraform {
  required_version = ">= 1.6.0"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.49"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.52"
    }
  }

  # Remote state belongs in R2 or S3. Leave this commented until the bucket
  # exists, otherwise `terraform init` asks for credentials you do not have yet.
  #
  # backend "s3" {
  #   bucket                      = "videomind-tfstate"
  #   key                         = "videomind/terraform.tfstate"
  #   region                      = "auto"
  #   skip_credentials_validation = true
  #   skip_requesting_account_id  = true
  #   skip_metadata_api_check     = true
  #   skip_region_validation      = true
  #   skip_s3_checksum            = true
  # }
}
