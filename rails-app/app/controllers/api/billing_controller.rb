module Api
  class BillingController < ApplicationController
    before_action :authenticate_request, only: :checkout

    def plans
      render json: StripeBilling::PLANS
    end

    def checkout
      plan = params[:plan].to_s
      return render json: { detail: "Unknown plan: #{plan}" }, status: :unprocessable_entity unless StripeBilling::PLANS.key?(plan)

      if plan == "free"
        current_user.update!(plan: "free", provider: "stripe", provider_id: nil, status: "active", current_period_end: nil)
        return render json: { configured: true, plan: "free", status: "active" }
      end

      render json: StripeBilling.checkout(plan:, user: current_user, base_url: request.base_url.chomp("/"))
    rescue StripeBilling::LiveKeyRefused => error
      render json: { detail: error.message }, status: :forbidden
    rescue StripeBilling::Error => error
      render json: { detail: error.message }, status: :bad_gateway
    end

    def stripe_webhook
      secret = ENV["STRIPE_WEBHOOK_SECRET"].to_s.strip
      return render json: { detail: "Webhook secret not configured" }, status: :service_unavailable if secret.empty?

      raw_body = request.raw_post
      unless StripeBilling.valid_signature?(raw_body, request.headers["Stripe-Signature"].to_s, secret)
        return render json: { detail: "Invalid Stripe signature" }, status: :bad_request
      end

      event = JSON.parse(raw_body)
      object = event.dig("data", "object") || {}
      metadata = object["metadata"] || {}
      user = User.find_by(id: object["client_reference_id"] || metadata["user_id"])
      plan = metadata["plan"]

      if event["type"] == "checkout.session.completed" && user && StripeBilling.paid_plan?(plan)
        user.update!(
          plan:,
          provider: "stripe",
          provider_id: object["subscription"],
          stripe_customer_id: object["customer"],
          status: "active",
          current_period_end: 30.days.from_now
        )
        return render json: { ok: true, activated: plan }
      end

      if event["type"] == "customer.subscription.deleted" && user
        user.update!(plan: "free", provider: "stripe", provider_id: object["id"], status: "cancelled", current_period_end: nil)
        return render json: { ok: true, cancelled: true }
      end

      render json: { ok: true, ignored: true, event: event["type"].to_s }
    rescue JSON::ParserError
      render json: { detail: "Malformed webhook body" }, status: :bad_request
    end
  end
end
