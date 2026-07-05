resource "google_workflows_workflow" "ff14_pipeline" {
  name            = "ff14-pf-pipeline"
  region          = var.region
  description     = "On-demand pipeline: duty-extractor -> Dataform. Triggered by the loader Cloud Run job after a successful load (not scheduled)."
  service_account = google_service_account.pipeline.email

  # The Cloud Run connector (googleapis.run.v2...jobs.run) BLOCKS until each job
  # finishes, guaranteeing the duty-extractor refreshes raw_duties before Dataform runs.
  source_contents = <<-EOF
    main:
      steps:

        - init:
            assign:
              - project: "${var.project_id}"
              - region: "${var.region}"

        - run_duty_extractor:
            call: googleapis.run.v2.projects.locations.jobs.run
            args:
              name: $${"projects/" + project + "/locations/" + region + "/jobs/ff14-pf-duty-extractor"}
            result: duty_result

        - run_dataform:
            call: googleapis.run.v2.projects.locations.jobs.run
            args:
              name: $${"projects/" + project + "/locations/" + region + "/jobs/ff14-pf-dataform-runner"}
            result: dataform_result

        - done:
            return: $${dataform_result}
  EOF

  depends_on = [
    google_cloud_run_v2_job.duty_extractor,
    google_cloud_run_v2_job.dataform_runner,
    google_service_account.pipeline,
  ]
}
