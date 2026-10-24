import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium

# Cấu hình web
st.set_page_config(page_title="Demo Milk-Run", layout="wide")
st.title("🚛 Hệ thống xếp tuyến Milk-Run tự động (Bản đồ trực quan)")

# 1. ĐỌC DỮ LIỆU TỪ EXCEL (Đã tắt cache để dữ liệu luôn mới)
def load_data():
    df_ncc = pd.read_excel('MilkRun_Data.xlsx', sheet_name='nha_cung_cap')
    df_donhang = pd.read_excel('MilkRun_Data.xlsx', sheet_name='don_hang')
    df_xe = pd.read_excel('MilkRun_Data.xlsx', sheet_name='xe_tai')
    
    # Xử lý tọa độ 
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

# 2. CHẠY THUẬT TOÁN ĐỊNH TUYẾN VÀ VẼ BẢN ĐỒ
if st.button("🚀 CHẠY THUẬT TOÁN MILK-RUN THỰC TẾ"):
    with st.spinner("Đang kết nối bản đồ thực tế, xếp xe và vẽ lộ trình..."):
        try:
            # Tính tổng nhu cầu (số Pallet)
            demands = [0] * len(df_ncc)
            for index, row in df_donhang.iterrows():
                ma_ncc = row['Mã NCC']
                pallet = row['Khối lượng (Pallet)']
                idx_ncc = df_ncc[df_ncc['Mã NCC'] == ma_ncc].index
                if len(idx_ncc) > 0:
                    demands[idx_ncc[0]] += pallet

            # Lấy ma trận khoảng cách từ OSRM
            coords = ";".join([f"{lon},{lat}" for lon, lat in zip(df_ncc['Kinh độ (Long)'], df_ncc['Vĩ độ (Lat)'])])
            url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=distance"
            headers = {'User-Agent': 'MilkRunDemo/1.0'}
            response = requests.get(url, headers=headers).json()
            
            distance_matrix = []
            for row in response['distances']:
                distance_matrix.append([int(val / 1000) for val in row])

            # Thuật toán tự chia tuyến
            vehicle_capacities = df_xe['Trọng tải (Số Pallet tối đa)'].tolist()
            num_vehicles = len(vehicle_capacities)
            unvisited = [i for i in range(1, len(df_ncc)) if demands[i] > 0]
            routes = []
            
            for v_id in range(num_vehicles):
                capacity = vehicle_capacities[v_id]
                current_node = 0  
                route_path = [0]
                route_load = 0
                route_dist = 0
                
                while unvisited:
                    best_node = None
                    best_dist = float('inf')
                    for node in unvisited:
                        if demands[node] <= capacity - route_load:
                            if distance_matrix[current_node][node] < best_dist:
                                best_dist = distance_matrix[current_node][node]
                                best_node = node
                    if best_node is None:
                        break 
                        
                    route_path.append(best_node)
                    route_load += demands[best_node]
                    route_dist += best_dist
                    current_node = best_node
                    unvisited.remove(best_node)
                    
                if len(route_path) > 1:
                    route_dist += distance_matrix[current_node][0]
                    route_path.append(0)
                    routes.append({
                        'v_id': v_id,
                        'path': route_path,
                        'load': route_load,
                        'dist': route_dist
                    })

            # TẠO BẢN ĐỒ TRỰC QUAN
            if routes:
                st.success("🎉 Đã tính toán xong! Xem thông số lộ trình và bản đồ thực tế bên dưới:")
                
                # Khởi tạo bản đồ trung tâm tại Nhà máy TMV
                depot_lat = df_ncc.iloc[0]['Vĩ độ (Lat)']
                depot_lon = df_ncc.iloc[0]['Kinh độ (Long)']
                m = folium.Map(location=[depot_lat, depot_lon], zoom_start=11)
                
                # Cắm cờ đỏ cho Nhà máy
                folium.Marker(
                    [depot_lat, depot_lon],
                    popup=f"<b>{df_ncc.iloc[0]['Tên Cơ Sở']}</b>",
                    icon=folium.Icon(color="red", icon="home"),
                    tooltip="Nhà máy TMV"
                ).add_to(m)
                
                # Cắm cờ xanh cho các Nhà cung cấp
                for i in range(1, len(df_ncc)):
                    if demands[i] > 0:
                        folium.Marker(
                            [df_ncc.iloc[i]['Vĩ độ (Lat)'], df_ncc.iloc[i]['Kinh độ (Long)']],
                            popup=f"<b>{df_ncc.iloc[i]['Tên Cơ Sở']}</b><br>Cần lấy: {demands[i]} Pallet",
                            icon=folium.Icon(color="blue", icon="info-sign"),
                            tooltip=df_ncc.iloc[i]['Tên Cơ Sở']
                        ).add_to(m)

                # Màu sắc phân biệt cho các tuyến xe khác nhau
                colors = ['blue', 'green', 'purple', 'orange', 'darkred']
                
                # In thông số và Vẽ nét nối lộ trình
                for r in routes:
                    v_id = r['v_id']
                    path_names = [df_ncc.iloc[n]['Tên Cơ Sở'] for n in r['path']]
                    
                    st.write(f"### 📍 Tuyến xe số {v_id + 1}: {df_xe.iloc[v_id]['Biển số']}")
                    st.info(" ➡️ ".join(path_names))
                    st.write(f"- 📦 Số hàng gom được: **{r['load']} / {vehicle_capacities[v_id]} Pallet**")
                    st.write(f"- 🛣️ Quãng đường di chuyển: **{r['dist']} km**")
                    st.write("---")
                    
                    # Lấy danh sách tọa độ để vẽ đường
                    path_coords = [[df_ncc.iloc[n]['Vĩ độ (Lat)'], df_ncc.iloc[n]['Kinh độ (Long)']] for n in r['path']]
                    folium.PolyLine(
                        path_coords,
                        color=colors[v_id % len(colors)],
                        weight=4,
                        opacity=0.8,
                        tooltip=f"Tuyến xe {v_id + 1}"
                    ).add_to(m)
                
                # Hiển thị bản đồ lên web
                st.write("### 🗺️ BẢN ĐỒ LỘ TRÌNH MILK-RUN")
                st_folium(m, width=1000, height=600)
                
                if unvisited:
                    st.warning(f"⚠️ Còn {len(unvisited)} nhà cung cấp chưa được gom hàng do đội xe không đủ tải trọng!")
                else:
                    st.balloons()
            else:
                st.error("⚠️ Không tìm được đường! Vui lòng kiểm tra lại tải trọng xe.")
        
        except Exception as e:
            st.error(f"⚠️ Có lỗi xảy ra trong quá trình tính toán và vẽ bản đồ: {e}")
