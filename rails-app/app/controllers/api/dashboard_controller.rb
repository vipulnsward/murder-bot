module Api
  class DashboardController < ApplicationController
    before_action :authenticate_request

    def status
      render json: {
        user: current_user.as_json(only: %i[email plan]),
        brain: { url: BrainClient.url, reachable: BrainClient.reachable? }
      }
    end
  end
end
