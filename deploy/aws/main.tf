# deVeres — single-host AWS infra (skeleton).
# Locks all inbound to the client's office CIDRs. `terraform apply` after
# `aws configure`. Intentionally minimal: one VPC, one public subnet, one EC2.

terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.region
}

variable "region"       { default = "eu-west-1" }
variable "client_cidrs" { type = list(string) }          # office egress IPs, e.g. ["203.0.113.10/32"]
variable "key_name"     { type = string }                # existing EC2 keypair
variable "instance_type" { default = "t3.medium" }

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
}

resource "aws_vpc" "main" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_hostnames = true
  tags = { Name = "deveres-vpc" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.1.0/24"
  map_public_ip_on_launch = true
  tags = { Name = "deveres-public" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "app" {
  name        = "deveres-app"
  description = "Client-office access only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from client office"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.client_cidrs
  }
  ingress {
    description = "SSH from client office / ops"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.client_cidrs
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "deveres-app" }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.app.id]
  key_name               = var.key_name

  root_block_device {
    volume_size = 40
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = <<-EOF
    #!/bin/bash
    apt-get update
    apt-get install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx git awscli
    systemctl enable --now docker
  EOF

  tags = { Name = "deveres-recon" }
}

resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
}

resource "aws_s3_bucket" "backups" {
  bucket = "deveres-backups-${var.region}"
  tags   = { Name = "deveres-backups" }
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id
  versioning_configuration { status = "Enabled" }
}

output "app_public_ip" { value = aws_eip.app.public_ip }
output "backups_bucket" { value = aws_s3_bucket.backups.bucket }
