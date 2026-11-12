from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Order
from ..generate_dealsure import verify_delivery_with_ai, release_escrow_funds
import json

@csrf_exempt
def submit_proof_and_claim(request, order_id):
    if request.method == "POST":
        data = json.loads(request.body)
        proof_text = data.get("proof_text")
        
        try:
            order = Order.objects.get(id=order_id, status='FUNDED')
        except Order.DoesNotExist:
            return JsonResponse({"error": "Order not found or not funded."}, status=404)

        # 1. Ask OpenAI if the proof is valid
        is_valid = verify_delivery_with_ai(order.title, proof_text)

        if not is_valid:
            return JsonResponse({"error": "AI Oracle rejected the proof of delivery."}, status=400)

        # 2. If valid, trigger the Stellar payout
        try:
            tx_response = release_escrow_funds(order)
            order.status = 'COMPLETED'
            order.save()
            
            return JsonResponse({
                "message": "Delivery verified. Funds released!",
                "tx_hash": tx_response["hash"]
            })
        except Exception as e:
            return JsonResponse({"error": f"Stellar transaction failed: {str(e)}"}, status=500)

    return JsonResponse({"error": "Invalid request"}, status=400)