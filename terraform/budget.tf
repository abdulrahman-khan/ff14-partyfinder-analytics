# =============================================================================
# Cost guardrail: monthly billing budget with email alerts
# =============================================================================
# $5/month budget, alerts only (no hard cap). A GCP budget NOTIFIES, it does not
# stop spending. Realistic steady-state spend for this pipeline is ~$0-2/mo, so
# 50% ($2.50) is an early warning and 100% ($5.00) means something is wrong.
#
# Alerts route to the same email channel as the failure alerts in monitoring.tf.

resource "google_project_service" "billingbudgets" {
  service            = "billingbudgets.googleapis.com"
  disable_on_destroy = false
}

# Resolve the project number, which the budget filter requires.
data "google_project" "current" {
  project_id = var.project_id
}

resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account
  display_name    = "FF14 PF Monthly Budget"

  budget_filter {
    projects               = ["projects/${data.google_project.current.number}"]
    calendar_period        = "MONTH"
    credit_types_treatment = "INCLUDE_ALL_CREDITS"
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = "5"
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }

  all_updates_rule {
    monitoring_notification_channels = [google_monitoring_notification_channel.email.id]
    disable_default_iam_recipients   = false
  }

  depends_on = [google_project_service.billingbudgets]
}
