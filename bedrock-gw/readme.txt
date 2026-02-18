aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin 982170164096.dkr.ecr.us-east-2.amazonaws.com
docker build -t bedrock-access-gateway /home/admin/staging/openwui-test/bedrock-gw/bedrock-access-gateway/src/
docker tag bedrock-access-gateway:latest 982170164096.dkr.ecr.us-east-2.amazonaws.com/bedrock-access-gateway:latest
docker push 982170164096.dkr.ecr.us-east-2.amazonaws.com/bedrock-access-gateway:latest