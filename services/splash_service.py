import os
import splash_pb2
import splash_pb2_grpc
from database import get_db_connection
from services.price_service import MarketPriceService
from services.rag_service import RAGService

HTTP_PORT = 8000
SERVER_IP = "10.151.13.241"  # Change this to your server's IP address

class SplashService(splash_pb2_grpc.SplashServiceServicer):
    
    # 🟢 1. Splash Init Data Endpoint
    def GetSplashInitData(self, request, context):
        print(f"📥 Client Connected: Version {request.client_version} on {request.device_platform}")
        
        response = splash_pb2.SplashDataResponse(
            is_success=True,
            message="Data fetched successfully"
        )
        
        try:
            db = get_db_connection()
            cursor = db.cursor(dictionary=True)
            
            # Fetch Books
            cursor.execute("SELECT * FROM books WHERE delete_at IS NULL")
            for b in cursor.fetchall():
                book = response.books.add()
                book.id = b['id']
                book.name = b['name'] or ""
                book.image_path = b['image_path'] or ""
                book.file_path = b['file_path'] or ""
                book.create_at = str(b['create_at']) if b['create_at'] else ""
                book.update_at = str(b['update_at']) if b['update_at'] else ""
                book.delete_at = str(b['delete_at']) if b['delete_at'] else ""

            # Fetch Shops
            cursor.execute("SELECT * FROM shops WHERE delete_at IS NULL")
            for s in cursor.fetchall():
                shop = response.shops.add()
                shop.id = s['id']
                shop.name = s['name'] or ""
                shop.address = s['address'] or ""
                shop.phone = s['phone'] or ""
                shop.type = s['type'] or ""
                shop.latitude = float(s['latitude']) if s['latitude'] is not None else 0.0
                shop.longitude = float(s['longitude']) if s['longitude'] is not None else 0.0
                shop.create_at = str(s['create_at']) if s['create_at'] else ""
                shop.update_at = str(s['update_at']) if s['update_at'] else ""
                shop.delete_at = str(s['delete_at']) if s['delete_at'] else ""

            # Fetch Media
            cursor.execute("SELECT * FROM media WHERE delete_at IS NULL")
            for m in cursor.fetchall():
                media = response.media_list.add()
                media.id = m['id']
                media.description = m['description'] or ""
                media.link = m['link'] or ""
                media.type = m['type'] or "news"
                media.create_at = str(m['create_at']) if m['create_at'] else ""
                media.update_at = str(m['update_at']) if m['update_at'] else ""
                media.delete_at = str(m['delete_at']) if m['delete_at'] else ""

            cursor.close()
            db.close()

            # Price Scrape
            MarketPriceService.fetch_and_save_excel()

            # Price Excel Links
            price_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "price")
            if os.path.exists(price_dir):
                for file_name in os.listdir(price_dir):
                    if file_name.endswith('.xlsx') or file_name.endswith('.xls'):
                        download_url = f"http://{SERVER_IP}:{HTTP_PORT}/files/price/{file_name}"
                        excel_item = response.price_excel.add()
                        excel_item.file_name = file_name
                        excel_item.download_url = download_url

            return response

        except Exception as e:
            print(f"❌ Error in GetSplashInitData: {e}")
            return splash_pb2.SplashDataResponse(
                is_success=False,
                message=f"Server Error: {str(e)}"
            )

    # 🟢 2. RAG Chat Endpoint (Flutter App မှ မေးခွန်းများဖြေကြားရန်)
    def AskRAGChat(self, request, context):
        user_query = request.user_query
        print(f"💬 Flutter User Query Received: {user_query}")

        if not user_query.strip():
            return splash_pb2.ChatResponse(is_success=False, answer="ကျေးဇူးပြု၍ မေးခွန်း ရေးသားပေးပါ။")

        answer = RAGService.answer_query(user_query)

        return splash_pb2.ChatResponse(
            is_success=True,
            answer=answer
        )