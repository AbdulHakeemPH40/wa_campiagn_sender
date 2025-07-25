# Replace the paypal_return function in userpanel/views.py with this:

def paypal_return(request):
    """Handle PayPal return - NCP buttons don't need execution"""
    try:
        # Get PayPal parameters
        payment_id = request.GET.get('paymentId')
        token = request.GET.get('token')
        payer_id = request.GET.get('PayerID')
        tx = request.GET.get('tx')
        st = request.GET.get('st')

        logger.info(f"PayPal return: paymentId={payment_id}, token={token}, PayerID={payer_id}, tx={tx}, st={st}")

        # Find order
        order = None
        pending_order_id = request.session.get('pending_order_id')
        
        if request.user.is_authenticated and pending_order_id:
            order = Order.objects.filter(
                id=pending_order_id,
                user=request.user,
                status='pending'
            ).first()

        if not order:
            messages.error(request, "No pending order found.")
            return redirect('userpanel:dashboard')

        # For NCP buttons - mark as processing immediately (no execution needed)
        if tx or st == 'Completed':
            order.status = 'processing'
            order.paypal_txn_id = tx or token or f"ncp-{timezone.now().strftime('%Y%m%d%H%M%S')}"
            order.save()
            
            logger.info(f"NCP payment processed: {tx or token}")
            messages.success(request, "Payment processed! Your subscription will be activated shortly.")
        
        # For REST API payments - execute first
        elif payment_id and payer_id:
            from .paypal_utils import PayPalAPI
            paypal_api = PayPalAPI()
            
            execution_result = paypal_api.execute_payment(payment_id, payer_id)
            
            if execution_result and execution_result.get('state') == 'approved':
                order.status = 'processing'
                order.paypal_txn_id = payment_id
                order.save()
                
                logger.info(f"REST API payment executed: {payment_id}")
                messages.success(request, "Payment processed! Your subscription will be activated shortly.")
            else:
                logger.error(f"Payment execution failed: {execution_result}")
                messages.error(request, "Payment execution failed. Please try again.")
                return redirect('userpanel:cart')
        else:
            return paypal_cancel(request)

        # Clear session
        if 'pending_order_id' in request.session:
            del request.session['pending_order_id']
        if 'cart' in request.session:
            del request.session['cart']
        request.session.modified = True

        return redirect('userpanel:dashboard')

    except Exception as e:
        logger.error(f"PayPal return error: {e}")
        messages.error(request, "Payment processing error. Please contact support.")
        return redirect('userpanel:dashboard')