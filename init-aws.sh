#!/bin/bash
awslocal s3api create-bucket --bucket product-admin-uploads --region eu-west-1 --create-bucket-configuration LocationConstraint=eu-west-1
