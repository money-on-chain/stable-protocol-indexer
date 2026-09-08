# exit as soon as an error happen
set -e

# Build the indexer image and push it to AWS ECR.
#
# The same image also carries scripts/ (see Dockerfile), so the one-off OMOC
# historical backfill runs from it too - the ECS task definition just overrides
# the container command, e.g.:
#
#   command: ["python", "./scripts/backfill_omoc.py", "--config", "config.json", "--from-block", "<n>"]
#   env:     APP_MONGO_URI, APP_MONGO_DB, APP_CONNECTION_URI
#
# Use -n to push to a dedicated ECR repo for that task (otherwise the repo name
# is moc_indexer_<environment>).

usage() { echo "Usage: $0 -e <environment> -c <config file> -i <aws id> -r <aws region> [-n <ecr repo name>]" 1>&2; exit 1; }

while getopts ":e:c:i:r:n:" o; do
    case "${o}" in
        e)
            e=${OPTARG}
            (( e=="ec2_testnet" || e=="ec2_testnet_historic" || e=="ec2_mainnet" || e=="ec2_mainnet_historic" )) || usage
            case $e in
                ec2_testnet)
                    ENV=$e
                    ;;
                ec2_testnet_historic)
                    ENV=$e
                    ;;
                ec2_mainnet)
                    ENV=$e
                    ;;
                ec2_mainnet_historic)
                    ENV=$e
                    ;;
                *)
                    usage
                    ;;
            esac
            ;;
        c)
            c=${OPTARG}
            CONFIG_FILE=$c
            ;;
        i)
            i=${OPTARG}
            AWS_ID=$i
            ;;
        r)
            r=${OPTARG}
            AWS_REGION=$r
            ;;
        n)
            n=${OPTARG}
            IMAGE_NAME=$n
            ;;
        *)
            usage
            ;;
    esac
done
shift $((OPTIND-1))

if [ -z "${e}" ] || [ -z "${c}" ] || [ -z "${i}" ] || [ -z "${r}" ]; then
    usage
fi

# ECR repository / local image name. Defaults to moc_indexer_<environment>;
# override with -n to push the same build to a separate repo (e.g. the backfill task).
IMAGE_NAME=${IMAGE_NAME:-moc_indexer_$ENV}

docker image build -t $IMAGE_NAME -f Dockerfile --build-arg CONFIG=$CONFIG_FILE .

echo "Build done!"

# login into aws ecr (get-login was removed in AWS CLI v2)
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $AWS_ID.dkr.ecr.$AWS_REGION.amazonaws.com

echo "Logging to AWS done!"

docker tag $IMAGE_NAME:latest $AWS_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$IMAGE_NAME:latest

docker push $AWS_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$IMAGE_NAME:latest

echo "finish done!"
