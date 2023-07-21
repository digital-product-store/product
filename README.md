# product

visit localhost:8001/docs for swagger ui

## notes

```
docker-compose exec localstack awslocal s3api create-bucket --bucket product-admin-uploads --region eu-west-1 --create-bucket-configuration LocationConstraint=eu-west-1

docker-compose exec localstack awslocal s3 ls s3://product-admin-uploads
```
