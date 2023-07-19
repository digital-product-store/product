# product-admin

visit localhost:8000/docs for swagger ui

## notes

```
docker-compose exec localstack awslocal s3api create-bucket --bucket product-admin-uploads --region eu-west-1 --create-bucket-configuration LocationConstraint=eu-west-1

docker-compose exec localstack awslocal s3 ls s3://product-admin-uploads
```

```json
{
    "Location": "http://product-admin-uploads.s3.localhost.localstack.cloud:4566/"
}
```
