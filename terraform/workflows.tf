resource "google_workflows_workflow" "ff14_pipeline" {
  name            = "ff14-pf-pipeline"
  region          = var.region
  description     = "Hourly pipeline: GCS → Bronze loader → Dataform silver → Dataform gold"
  service_account = google_service_account.pipeline.email

  source_contents = <<-EOF
    main:
      steps:

        - init:
            assign:
              - project: "${var.project_id}"
              - region: "${var.region}"
              - job_name: "ff14-pf-loader"

        - run_loader:
            call: http.post
            args:
              url: $${"https://" + region + "-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/" + project + "/jobs/" + job_name + ":run"}
              auth:
                type: OAuth2
            result: loader_response

        - wait_for_loader:
            call: sys.sleep
            args:
              seconds: 120

        - run_dataform:
            call: http.post
            args:
              url: $${"https://dataform.googleapis.com/v1beta1/projects/" + project + "/locations/" + region + "/repositories/ff14-pf-dataform/compilationResults"}
              auth:
                type: OAuth2
              body:
                gitCommitish: "main"
            result: compilation_result

        - trigger_dataform_run:
            call: http.post
            args:
              url: $${"https://dataform.googleapis.com/v1beta1/projects/" + project + "/locations/" + region + "/repositories/ff14-pf-dataform/workflowInvocations"}
              auth:
                type: OAuth2
              body:
                compilationResult: $${compilation_result.body.name}
            result: invocation_result

        - done:
            return: $${invocation_result.body.name}
  EOF

  depends_on = [
    google_cloud_run_v2_job.loader,
    google_service_account.pipeline,
  ]
}

#  Scheduler: trigger the workflow hourly 
# 5 minutes past the hour, 
resource "google_cloud_scheduler_job" "pipeline_trigger" {
  name             = "ff14-pf-pipeline-trigger"
  description      = "Trigger the hourly FF14 pipeline workflow"
  schedule         = "5 * * * *"
  time_zone        = "UTC"
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "https://workflowexecutions.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/workflows/${google_workflows_workflow.ff14_pipeline.name}/executions"

    oauth_token {
      service_account_email = google_service_account.pipeline.email
    }
  }

  depends_on = [google_workflows_workflow.ff14_pipeline]
}