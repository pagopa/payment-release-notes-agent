{
  "openapi": "3.0.0",
  "info": {
    "title": "Payment Release Notes API",
    "description": "Async release notes generation from GitHub Pull Requests",
    "version": "v1"
  },
  "servers": [
    {
      "url": "https://${host}/${api_path}/v1"
    }
  ],
  "security": [
    {
      "ApiKeyHeader": []
    }
  ],
  "paths": {
    "/generate": {
      "post": {
        "operationId": "generateReleaseNotes",
        "summary": "Enqueue a release notes generation job",
        "description": "Starts an async job that generates a release notes PDF from a GitHub PR. Returns a job_id to poll via GET /status/{jobId}.",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/GenerateRequest"
              }
            }
          }
        },
        "responses": {
          "202": {
            "description": "Job accepted",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/GenerateResponse"
                }
              }
            }
          },
          "400": {
            "description": "Bad request — missing required fields",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ErrorResponse"
                }
              }
            }
          },
          "500": {
            "description": "Internal server error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ErrorResponse"
                }
              }
            }
          }
        }
      }
    },
    "/status/{jobId}": {
      "get": {
        "operationId": "getJobStatus",
        "summary": "Poll job status",
        "description": "Returns the current status of a generation job. When completed, includes a pre-signed URL to download the PDF (valid 1 hour).",
        "parameters": [
          {
            "name": "jobId",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid"
            },
            "description": "Job identifier returned by POST /generate"
          }
        ],
        "responses": {
          "200": {
            "description": "Job status",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/StatusResponse"
                }
              }
            }
          },
          "500": {
            "description": "Internal server error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ErrorResponse"
                }
              }
            }
          }
        }
      }
    }
  },
  "components": {
    "schemas": {
      "GenerateRequest": {
        "type": "object",
        "required": ["platform", "pr_number"],
        "properties": {
          "platform": {
            "type": "string",
            "description": "GitHub repository in owner/repo format",
            "example": "pagopa/my-service"
          },
          "pr_number": {
            "type": "string",
            "description": "Pull request number",
            "example": "42"
          },
          "version": {
            "type": "string",
            "description": "Release version label included in the document",
            "default": "1.0.0",
            "example": "1.2.3"
          },
          "jira_issue_key": {
            "type": "string",
            "description": "JIRA issue key — PDF will be attached as a comment (optional)",
            "example": "PROJ-123"
          },
          "confluence_space": {
            "type": "string",
            "description": "Confluence space key where the release page will be created (optional)",
            "example": "TEAM"
          },
          "confluence_parent_page": {
            "type": "string",
            "description": "Title of the Confluence parent page (optional)"
          },
          "confluence_page_title": {
            "type": "string",
            "description": "Title for the new Confluence page (optional)"
          }
        }
      },
      "GenerateResponse": {
        "type": "object",
        "properties": {
          "job_id": {
            "type": "string",
            "format": "uuid",
            "description": "Unique identifier for the enqueued job"
          },
          "status": {
            "type": "string",
            "enum": ["pending"]
          },
          "status_url": {
            "type": "string",
            "description": "Relative path to poll for job status"
          },
          "jira_issue_key": {
            "type": "string",
            "nullable": true
          },
          "confluence_space": {
            "type": "string",
            "nullable": true
          },
          "confluence_url": {
            "type": "string",
            "nullable": true,
            "description": "URL of the Confluence placeholder page created synchronously — present only when confluence_space is provided and Atlassian is configured"
          }
        }
      },
      "StatusResponse": {
        "type": "object",
        "properties": {
          "job_id": {
            "type": "string",
            "format": "uuid"
          },
          "status": {
            "type": "string",
            "enum": ["pending", "completed", "failed"]
          },
          "download_url": {
            "type": "string",
            "description": "Pre-signed Azure Blob URL to download the PDF — present only when status=completed, expires in 1 hour"
          },
          "error": {
            "type": "string",
            "description": "Error detail — present only when status=failed"
          }
        }
      },
      "ErrorResponse": {
        "type": "object",
        "properties": {
          "error": {
            "type": "string"
          }
        }
      }
    },
    "securitySchemes": {
      "ApiKeyHeader": {
        "type": "apiKey",
        "in": "header",
        "name": "Ocp-Apim-Subscription-Key"
      }
    }
  }
}
