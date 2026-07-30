module Authentication
  extend ActiveSupport::Concern

  private

  attr_reader :current_user

  def authenticate_request
    token = request.authorization.to_s.delete_prefix("Bearer ")
    payload, = JWT.decode(token, jwt_secret, true, algorithm: "HS256")
    @current_user = User.find(payload.fetch("sub"))
  rescue JWT::DecodeError, KeyError, ActiveRecord::RecordNotFound
    render json: { detail: "Authentication required" }, status: :unauthorized
  end

  def issue_token(user)
    JWT.encode({ sub: user.id.to_s, exp: 7.days.from_now.to_i }, jwt_secret, "HS256")
  end

  def jwt_secret
    ENV["SECRET"].presence || Rails.application.secret_key_base
  end
end
