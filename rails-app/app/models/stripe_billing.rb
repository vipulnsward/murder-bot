require "net/http"

class StripeBilling
  API_ROOT = "https://api.stripe.com/v1"
  PLANS = {
    "free" => {
      rank: 0,
      name: "Free",
      price_usd: 0,
      tagline: "View-only. See your roster and public intel.",
      features: [
        "Generals gallery + owned roster (read-only)",
        "World map viewer",
        "One Evony account linked",
        "No automation, no AI counter, no reports"
      ]
    },
    "brain" => {
      rank: 1,
      name: "Brain",
      price_usd: 5,
      tagline: "The AI edge Easy Bot doesn't have. No setup.",
      features: [
        "Unlimited AI counters (real battle sim)",
        "Enemy intel database",
        "Attack / favorable-trade planner",
        "Works instantly — no emulator needed"
      ]
    },
    "auto" => {
      rank: 2,
      name: "Auto",
      price_usd: 9,
      tagline: "The full bot for a single commander.",
      features: [
        "Everything in Brain",
        "Full 24/7 automation: rally, stamina top-up, kickout reclaim",
        "Battle-report scanning + parsed history",
        "One Evony account, fully automated"
      ]
    },
    "alliance" => {
      rank: 3,
      name: "Alliance",
      price_usd: 29,
      tagline: "Run the whole R4 desk: many accounts, intel on everyone.",
      features: [
        "Everything in Auto",
        "Multi-account control (up to 5 linked Evony accounts)",
        "Alliance-wide intel: scout + track every enemy you see",
        "Shared counter/PvP brain across accounts",
        "Priority scan cadence"
      ]
    }
  }.freeze

  class Error < StandardError; end
  class LiveKeyRefused < Error; end

  def self.checkout(plan:, user:, base_url:)
    secret = ENV["STRIPE_SECRET_KEY"].to_s.strip
    if secret.start_with?("sk_live_") && ENV["BILLING_LIVE"] != "1"
      raise LiveKeyRefused,
        "Refusing to create a LIVE Stripe resource. A live key (sk_live_...) is configured but BILLING_LIVE is not '1'."
    end

    price = ENV["STRIPE_PRICE_#{plan.upcase}"].to_s.strip
    if secret.empty? || price.empty?
      return {
        configured: false,
        message: "Stripe not configured yet. Set STRIPE_SECRET_KEY and STRIPE_PRICE_#{plan.upcase} to enable checkout."
      }
    end

    uri = URI("#{API_ROOT}/checkout/sessions")
    request = Net::HTTP::Post.new(uri)
    request["Authorization"] = "Bearer #{secret}"
    request.set_form_data(
      "mode" => "subscription",
      "line_items[0][price]" => price,
      "line_items[0][quantity]" => 1,
      "success_url" => "#{base_url}/billing?checkout=success",
      "cancel_url" => "#{base_url}/billing?checkout=cancel",
      "client_reference_id" => user.id,
      "metadata[plan]" => plan,
      "metadata[user_id]" => user.id,
      "subscription_data[metadata][plan]" => plan,
      "subscription_data[metadata][user_id]" => user.id,
      "allow_promotion_codes" => "true"
    )
    response = Net::HTTP.start(uri.host, uri.port, use_ssl: true, open_timeout: 15, read_timeout: 15) { |http| http.request(request) }
    raise Error, "Stripe error: #{response.body.to_s.first(300)}" unless response.is_a?(Net::HTTPSuccess)

    session = JSON.parse(response.body)
    {
      configured: true,
      url: session["url"],
      id: session["id"],
      provider: "stripe",
      mode: secret.start_with?("sk_live_") ? "live" : "test"
    }
  rescue JSON::ParserError, IOError, SystemCallError, Timeout::Error => error
    raise Error, "Stripe error: #{error.message}"
  end

  def self.valid_signature?(body, signature, secret)
    parts = signature.split(",").filter_map { |part| part.split("=", 2) if part.include?("=") }.to_h
    expected = OpenSSL::HMAC.hexdigest("SHA256", secret, "#{parts.fetch("t")}.#{body}")
    ActiveSupport::SecurityUtils.secure_compare(expected, parts.fetch("v1"))
  rescue KeyError
    false
  end

  def self.paid_plan?(plan)
    PLANS.key?(plan) && plan != "free"
  end
end
