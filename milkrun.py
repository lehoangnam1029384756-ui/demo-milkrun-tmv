import streamlit as st
import pandas as pd
import requests

# Cấu hình web
st.set_page_config(page_title="Demo Milk-Run", layout="wide")
st.title("🚛 Hệ thống xếp tuyến Milk-Run tự động (Bản đồ thực tế)")

# 1. ĐỌC DỮ LIỆU TỪ EXCEL

def load_data():
    df_ncc = pd.read_excel('MilkRun_Data.xlsx', sheet_name='nha_cung_cap')
    df_donhang = pd.read_excel('MilkRun_Data.xlsx', sheet_name='don_hang')
    df_xe = pd.read_excel('MilkRun_Data.xlsx', sheet_name='xe_tai')
    
    # Xử lý tọa độ để tránh lỗi định dạng
    df_ncc['Vĩ độ (Lat)'] = df_ncc['Vĩ độ (Lat)'].astype(str).str.replace(',', '.').astype(float)
    df_ncc['Kinh độ (Long)'] = df_ncc['Kinh độ (Long)'].astype(str).str.replace(',', '.').astype(float)
    return df_ncc, df_donhang, df_xe

df_ncc, df_donhang, df_xe = load_data()

st.sidebar.header("Dữ liệu đầu vào")
if st.sidebar.checkbox("1. Xem danh sách Nhà cung cấp"):
    st.dataframe(df_ncc)
if st.sidebar.checkbox("2. Xem tín hiệu e-Kanban (Đơn hàng)"):
    st.dataframe(df_donhang)
if st.sidebar.checkbox("3. Xem năng lực đội xe"):
    st.dataframe(df_xe)

st.write("---")
st.subheader("Bấm nút bên dưới để hệ thống quét bản đồ và tính tuyến đường")

# 2. CHẠY THUẬT TOÁN ĐỊNH TUYẾN
if st.button("🚀 CHẠY THUẬT TOÁN MILK-RUN THỰC TẾ"):
    with st.spinner("Đang kết nối bản đồ thực tế và xếp xe..."):
        try:
            # A. Tính tổng nhu cầu (số Pallet) cần gom ở mỗi nhà cung cấp
            demands = [0] * len(df_ncc)
            for index, row in df_donhang.iterrows():
                ma_ncc = row['Mã NCC']
                pallet = row['Khối lượng (Pallet)']
                idx_ncc = df_ncc[df_ncc['Mã NCC'] == ma_ncc].index
                if len(idx_ncc) > 0:
                    demands[idx_ncc[0]] += pallet

            # B. Lấy ma trận khoảng cách từ bản đồ OSRM (Open Source Routing Machine)
            coords = ";".join([f"{lon},{lat}" for lon, lat in zip(df_ncc['Kinh độ (Long)'], df_ncc['Vĩ độ (Lat)'])])
            url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=distance"
            headers = {'User-Agent': 'MilkRunDemo/1.0'}
            response = requests.get(url, headers=headers).json()
            
            # Chuyển đổi từ mét sang km
            distance_matrix = []
            for row in response['distances']:
                distance_matrix.append([int(val / 1000) for val in row])

            # C. Thuật toán tự chia tuyến (Greedy/Nearest Neighbor Routing)
            vehicle_capacities = df_xe['Trọng tải (Số Pallet tối đa)'].tolist()
            num_vehicles = len(vehicle_capacities)
            
            unvisited = [i for i in range(1, len(df_ncc)) if demands[i] > 0]
            routes = []
            
            for v_id in range(num_vehicles):
                capacity = vehicle_capacities[v_id]
                current_node = 0  # Bắt đầu từ Nhà máy (Index 0)
                route_path = [0]
                route_load = 0
                route_dist = 0
                
                while unvisited:
                    best_node = None
                    best_dist = float('inf')
                    
                    # Tìm nhà cung cấp gần nhất mà xe còn chở được
                    for node in unvisited:
                        if demands[node] <= capacity - route_load:
                            if distance_matrix[current_node][node] < best_dist:
                                best_dist = distance_matrix[current_node][node]
                                best_node = node
                    
                    if best_node is None:
                        break # Xe đã đầy hoặc không chở nổi kiện hàng tiếp theo
                        
                    route_path.append(best_node)
                    route_load += demands[best_node]
                    route_dist += best_dist
                    current_node = best_node
                    unvisited.remove(best_node)
                    
                # Tính đường quay về nhà máy
                if len(route_path) > 1:
                    route_dist += distance_matrix[current_node][0]
                    route_path.append(0)
                    routes.append({
                        'v_id': v_id,
                        'path': route_path,
                        'load': route_load,
                        'dist': route_dist
                    })

            # D. In kết quả ra màn hình web
            if routes:
                st.success("🎉 Đã tính toán xong! Dưới đây là lộ trình tối ưu nhất dựa trên bản đồ thực tế:")
                for r in routes:
                    v_id = r['v_id']
                    path_names = [df_ncc.iloc[n]['Tên Cơ Sở'] for n in r['path']]
                    
                    st.write(f"### 📍 Tuyến xe số {v_id + 1}: {df_xe.iloc[v_id]['Biển số']}")
                    st.info(" ➡️ ".join(path_names))
                    st.write(f"- 📦 Số hàng gom được: **{r['load']} / {vehicle_capacities[v_id]} Pallet**")
                    st.write(f"- 🛣️ Quãng đường di chuyển: **{r['dist']} km**")
                    st.write("---")
                
                if unvisited:
                    st.warning(f"⚠️ Còn {len(unvisited)} nhà cung cấp chưa được gom hàng do đội xe không đủ tải trọng!")
                else:
                    st.balloons()
            else:
                st.error("⚠️ Không thể tìm được đường! Vui lòng kiểm tra lại dữ liệu xe.")
        
        except Exception as e:
            st.error(f"⚠️ Có lỗi trong quá trình quét bản đồ: {e}")