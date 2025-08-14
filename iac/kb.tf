locals {
  embedding_model_arn = "arn:aws:bedrock:${local.region}::foundation-model/amazon.titan-embed-text-v2:0"
  knowledge_base_arn  = data.local_file.kb_arn.content
  knowledge_base_id   = data.local_file.kb_id.content
}

# creates a bedrock knowledge base
# (since s3 vectors support has not been added yet)
resource "null_resource" "bedrock_knowledge_base" {
  depends_on = [aws_iam_role_policy.kb]

  triggers = {
    region          = local.region
    name            = var.name
    description     = "kb for ${var.name}"
    kb_role_arn     = aws_iam_role.bedrock_kb_role.arn
    embedding_model = local.embedding_model_arn
    bucket_name     = aws_s3_bucket.main.bucket
    bucket_arn      = aws_s3_bucket.main.arn
  }

  provisioner "local-exec" {
    command = "sleep 10 && ./kb-create.sh"
    environment = {
      AWS_REGION      = self.triggers.region
      NAME            = self.triggers.name
      DESCRIPTION     = self.triggers.description
      KB_ROLE_ARN     = self.triggers.kb_role_arn
      EMBEDDING_MODEL = self.triggers.embedding_model
      BUCKET_NAME     = self.triggers.bucket_name
      BUCKET_ARN      = self.triggers.bucket_arn
    }
  }

  provisioner "local-exec" {
    when    = destroy
    command = "./kb-destroy.sh"
    environment = {
      AWS_REGION = self.triggers.region
      NAME       = self.triggers.name
    }
  }
}

# exposes the knowledge base arn
data "local_file" "kb_arn" {
  filename   = "kb-arn.txt"
  depends_on = [null_resource.bedrock_knowledge_base]
}

# exposes the knowledge base id
data "local_file" "kb_id" {
  filename   = "kb-id.txt"
  depends_on = [null_resource.bedrock_knowledge_base]
}

resource "aws_bedrockagent_data_source" "main" {
  knowledge_base_id = local.knowledge_base_id
  name              = aws_s3_bucket.main.bucket
  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = aws_s3_bucket.main.arn
    }
  }
  data_deletion_policy = "RETAIN"
}

resource "aws_iam_role" "bedrock_kb_role" {
  name               = "BedrockExecutionRoleForKnowledgeBase-${var.name}"
  assume_role_policy = data.aws_iam_policy_document.kb_assume.json
}

resource "aws_iam_role_policy" "kb" {
  role   = aws_iam_role.bedrock_kb_role.name
  policy = data.aws_iam_policy_document.kb.json
}

data "aws_iam_policy_document" "kb_assume" {
  statement {
    sid     = "AmazonBedrockKnowledgeBaseTrustPolicy"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:bedrock:${local.region}:${local.account_id}:knowledge-base/*"]
    }
  }
}

data "aws_iam_policy_document" "kb" {
  statement {
    sid       = "BedrockInvokeModelStatement"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.embedding_model_arn]
  }

  statement {
    sid       = "S3ListBucketStatement"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.main.arn]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [local.account_id]
    }
  }

  statement {
    sid       = "S3GetObjectStatement"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.main.arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [local.account_id]
    }
  }

  statement {
    sid    = "S3VectorsStatement"
    effect = "Allow"
    actions = [
      "s3vectors:QueryVectors",
      "s3vectors:PutVectors",
      "s3vectors:DeleteVectors",
      "s3vectors:GetVectors",
      "s3vectors:ListVectors",
      "s3vectors:GetIndex",
      "s3vectors:ListIndexes",
      "s3vectors:GetVectorBucket",
      "s3vectors:ListVectorBuckets"
    ]
    resources = [
      "arn:aws:s3vectors:${local.region}:${local.account_id}:bucket/${var.name}-vectors",
      "arn:aws:s3vectors:${local.region}:${local.account_id}:bucket/${var.name}-vectors/*"
    ]
  }
}
