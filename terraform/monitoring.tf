# =============================================================================
# Observability: failure alerting for the FF14-PF pipeline
# =============================================================================
# One email notification channel + alert policies covering scraper, loader,
# duty-extractor, Workflows, and Dataform.
#
# Design note: the loader catches per-file errors and the scraper's
# "zero listings parsed" case both exit 0, so a job-failure metric alone misses
# the most important failures. Log-based alerts (policies 1, 2, 5) carry most of
# the weight; the metric alerts (3, 4) are belt-and-suspenders for hard crashes.

resource "google_project_service" "monitoring" {
  service            = "monitoring.googleapis.com"
  disable_on_destroy = false
}

# -- Notification channel ------------------------------------------------------
resource "google_monitoring_notification_channel" "email" {
  display_name = "FF14 PF Alerts"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }

  depends_on = [google_project_service.monitoring]
}

# -- 1. Scraper dead-letter written (xivpf.com HTML changed / zero listings) ---
# Highest value: the scraper writes a dead-letter and still exits 0 when it
# parses zero listings, so this is the only signal that catches a silent break.
resource "google_monitoring_alert_policy" "dead_letter" {
  display_name = "FF14: scraper dead-letter written"
  combiner     = "OR"

  conditions {
    display_name = "Dead-letter record written to GCS"
    condition_matched_log {
      filter = "resource.type=\"cloud_run_job\" AND textPayload:\"Dead-letter record written\""
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = "3600s"
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]
  depends_on            = [google_project_service.monitoring]
}

# -- 2. Any pipeline ERROR log (loader soft failures, scraper hard errors) -----
resource "google_monitoring_alert_policy" "cloud_run_error_log" {
  display_name = "FF14: pipeline ERROR log"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run job logged an ERROR"
    condition_matched_log {
      filter = "resource.type=\"cloud_run_job\" AND severity>=ERROR"
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = "3600s"
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]
  depends_on            = [google_project_service.monitoring]
}

# -- 3. Cloud Run job hard failure (crash / OOM / timeout) ---------------------
resource "google_monitoring_alert_policy" "cloud_run_job_failed" {
  display_name = "FF14: Cloud Run job execution failed"
  combiner     = "OR"

  conditions {
    display_name = "A job execution finished with result=failed"
    condition_threshold {
      filter          = "resource.type = \"cloud_run_job\" AND metric.type = \"run.googleapis.com/job/completed_execution_count\" AND metric.labels.result = \"failed\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]
  depends_on            = [google_project_service.monitoring]
}

# -- 4. Workflow execution failed (orchestration broke) -----------------------
resource "google_monitoring_alert_policy" "workflow_failed" {
  display_name = "FF14: Workflow execution failed"
  combiner     = "OR"

  conditions {
    display_name = "A workflow execution finished with status=FAILED"
    condition_threshold {
      filter          = "resource.type = \"workflows.googleapis.com/Workflow\" AND metric.type = \"workflows.googleapis.com/finished_execution_count\" AND metric.labels.status = \"FAILED\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]
  depends_on            = [google_project_service.monitoring]
}

# -- 5. Dataform invocation failed (transforms + future assertions) -----------
# The workflow fires Dataform fire-and-forget, so a failed Dataform invocation
# (incl. assertion failures) never propagates to the workflow status. Alert on
# Dataform's own logs instead of relying on policy 4.
resource "google_monitoring_alert_policy" "dataform_failed" {
  display_name = "FF14: Dataform invocation failed"
  combiner     = "OR"

  conditions {
    display_name = "Dataform repository logged an ERROR"
    condition_matched_log {
      filter = "resource.type=\"dataform.googleapis.com/Repository\" AND severity>=ERROR"
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = "3600s"
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]
  depends_on            = [google_project_service.monitoring]
}
