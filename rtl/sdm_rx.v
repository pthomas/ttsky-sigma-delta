// sdm_rx -- bitstream receiver / dual-path sinc3 decimator with an
// AXI4-Lite register interface.
//
// Fabric-side companion for the TT sigma-delta modulator: one raw
// 1-bit stream in, two concurrent decimated paths out (fast/coarse
// for protection, slow/precise for measurement), matching the
// dual-OSR usage the chip's datasheet describes. Single clock
// domain: aclk is also the modulator bit clock (the FPGA drives the
// chip's clk; board-level capture phase is handled at the IO). Tie
// bit_ce high for one bit per clock, or pulse it to divide.
//
// Register map (32-bit, byte addresses):
//   0x00 R  ID        0x53444D31 "SDM1"
//   0x04 R  VERSION   0x0000_0100
//   0x08 RW CTRL      bit0 enable, bit1 clear (self-clearing)
//   0x0C RW OSR_FAST  decimation ratio, fast path (default 25)
//   0x10 RW OSR_PREC  decimation ratio, precision path (default 250)
//   0x14 RW1C STATUS  bit0 fast sample valid, bit1 prec sample valid
//   0x18 R  DATA_FAST last fast-path sample (signed)
//   0x1C R  DATA_PREC last precision-path sample (signed)
//   0x20 R  COUNT_FAST fast samples produced since clear
//   0x24 R  COUNT_PREC precision samples produced since clear
//   0x28 R  BITS_TOTAL bits consumed since clear
//   0x2C R  BITS_ONES  ones among them (ones density = 0x2C/0x28,
//                      the same health metric the chip's acceptance
//                      sims gate on)
//
// sinc3: per path, 3 integrators at bit rate on the +/-1-mapped bit,
// 3 combs at the decimated rate. DC full scale = OSR^3. Internal
// state is 40 bits; outputs expose the low 32 (exact for OSR <= 1024).
// The first 3 output samples after enable/clear are filter settling;
// the testbench's golden model reproduces them bit-exactly.
//
// OSR registers are sampled into the path logic only at CTRL.clear,
// so a mid-run write cannot glitch a sample.

`default_nettype none

module sdm_rx #(
    parameter ACC_W = 40
) (
    input  wire        aclk,
    input  wire        aresetn,

    // modulator bitstream
    input  wire        bit_i,
    input  wire        bit_ce,

    // AXI4-Lite slave
    input  wire [7:0]  s_axil_awaddr,
    input  wire        s_axil_awvalid,
    output wire        s_axil_awready,
    input  wire [31:0] s_axil_wdata,
    input  wire [3:0]  s_axil_wstrb,
    input  wire        s_axil_wvalid,
    output wire        s_axil_wready,
    output wire [1:0]  s_axil_bresp,
    output reg         s_axil_bvalid,
    input  wire        s_axil_bready,
    input  wire [7:0]  s_axil_araddr,
    input  wire        s_axil_arvalid,
    output wire        s_axil_arready,
    output reg  [31:0] s_axil_rdata,
    output wire [1:0]  s_axil_rresp,
    output reg         s_axil_rvalid,
    input  wire        s_axil_rready
);

    // ------------------------------------------------------- registers
    reg        ctrl_enable;
    reg [15:0] osr_fast_cfg, osr_prec_cfg;
    reg        clear_pulse;

    reg [15:0] osr_fast, osr_prec;      // active copies, load on clear

    reg signed [31:0] data_fast, data_prec;
    reg        fast_valid, prec_valid;
    reg [31:0] count_fast, count_prec;
    reg [31:0] bits_total, bits_ones;

    // --------------------------------------------------- write channel
    reg aw_hs, w_hs;                    // captured handshakes
    reg [7:0]  awaddr_q;
    reg [31:0] wdata_q;

    assign s_axil_awready = !aw_hs && !s_axil_bvalid;
    assign s_axil_wready  = !w_hs && !s_axil_bvalid;
    assign s_axil_bresp   = 2'b00;

    wire do_write = aw_hs && w_hs;

    always @(posedge aclk) begin
        if (!aresetn) begin
            aw_hs <= 1'b0;
            w_hs  <= 1'b0;
            s_axil_bvalid <= 1'b0;
            ctrl_enable  <= 1'b0;
            osr_fast_cfg <= 16'd25;
            osr_prec_cfg <= 16'd250;
            clear_pulse  <= 1'b0;
            fast_valid   <= 1'b0;
            prec_valid   <= 1'b0;
        end else begin
            clear_pulse <= 1'b0;

            if (s_axil_awvalid && s_axil_awready) begin
                aw_hs    <= 1'b1;
                awaddr_q <= s_axil_awaddr;
            end
            if (s_axil_wvalid && s_axil_wready) begin
                w_hs    <= 1'b1;
                wdata_q <= s_axil_wdata;
            end

            if (do_write) begin
                aw_hs <= 1'b0;
                w_hs  <= 1'b0;
                s_axil_bvalid <= 1'b1;
                case (awaddr_q[7:2])
                    6'h02: begin                       // CTRL
                        ctrl_enable <= wdata_q[0];
                        clear_pulse <= wdata_q[1];
                    end
                    6'h03: osr_fast_cfg <= wdata_q[15:0];
                    6'h04: osr_prec_cfg <= wdata_q[15:0];
                    6'h05: begin                       // STATUS W1C
                        if (wdata_q[0]) fast_valid <= 1'b0;
                        if (wdata_q[1]) prec_valid <= 1'b0;
                    end
                    default: ;
                endcase
            end else if (s_axil_bvalid && s_axil_bready)
                s_axil_bvalid <= 1'b0;

            if (fast_strobe) fast_valid <= 1'b1;
            if (prec_strobe) prec_valid <= 1'b1;
        end
    end

    // ---------------------------------------------------- read channel
    assign s_axil_arready = !s_axil_rvalid;
    assign s_axil_rresp   = 2'b00;

    always @(posedge aclk) begin
        if (!aresetn) begin
            s_axil_rvalid <= 1'b0;
        end else if (s_axil_arvalid && s_axil_arready) begin
            s_axil_rvalid <= 1'b1;
            case (s_axil_araddr[7:2])
                6'h00: s_axil_rdata <= 32'h53444D31;
                6'h01: s_axil_rdata <= 32'h0000_0100;
                6'h02: s_axil_rdata <= {31'b0, ctrl_enable};
                6'h03: s_axil_rdata <= {16'b0, osr_fast_cfg};
                6'h04: s_axil_rdata <= {16'b0, osr_prec_cfg};
                6'h05: s_axil_rdata <= {30'b0, prec_valid, fast_valid};
                6'h06: s_axil_rdata <= data_fast;
                6'h07: s_axil_rdata <= data_prec;
                6'h08: s_axil_rdata <= count_fast;
                6'h09: s_axil_rdata <= count_prec;
                6'h0A: s_axil_rdata <= bits_total;
                6'h0B: s_axil_rdata <= bits_ones;
                default: s_axil_rdata <= 32'h0;
            endcase
        end else if (s_axil_rvalid && s_axil_rready)
            s_axil_rvalid <= 1'b0;
    end

    // -------------------------------------------- sinc3 path machinery
    wire signed [1:0] din = bit_i ? 2'sd1 : -2'sd1;
    wire step = ctrl_enable && bit_ce;

    reg fast_strobe, prec_strobe;

    // fast path
    reg signed [ACC_W-1:0] f_i1, f_i2, f_i3;
    reg signed [ACC_W-1:0] f_z1, f_z2, f_z3;
    reg [15:0] f_cnt;

    // precision path
    reg signed [ACC_W-1:0] p_i1, p_i2, p_i3;
    reg signed [ACC_W-1:0] p_z1, p_z2, p_z3;
    reg [15:0] p_cnt;

    // comb intermediates (combinational)
    wire signed [ACC_W-1:0] f_c1 = f_i3 - f_z1;
    wire signed [ACC_W-1:0] f_c2 = f_c1 - f_z2;
    wire signed [ACC_W-1:0] f_c3 = f_c2 - f_z3;
    wire signed [ACC_W-1:0] p_c1 = p_i3 - p_z1;
    wire signed [ACC_W-1:0] p_c2 = p_c1 - p_z2;
    wire signed [ACC_W-1:0] p_c3 = p_c2 - p_z3;

    always @(posedge aclk) begin
        if (!aresetn || clear_pulse) begin
            {f_i1, f_i2, f_i3, f_z1, f_z2, f_z3} <= 0;
            {p_i1, p_i2, p_i3, p_z1, p_z2, p_z3} <= 0;
            f_cnt <= 16'd0;
            p_cnt <= 16'd0;
            osr_fast <= osr_fast_cfg;
            osr_prec <= osr_prec_cfg;
            data_fast <= 32'sd0;
            data_prec <= 32'sd0;
            count_fast <= 32'd0;
            count_prec <= 32'd0;
            bits_total <= 32'd0;
            bits_ones  <= 32'd0;
            fast_strobe <= 1'b0;
            prec_strobe <= 1'b0;
        end else begin
            fast_strobe <= 1'b0;
            prec_strobe <= 1'b0;
            if (step) begin
                bits_total <= bits_total + 32'd1;
                if (bit_i) bits_ones <= bits_ones + 32'd1;

                // integrate (order matters: i3 uses previous i2 etc.
                // -- classic CIC; the golden model mirrors this)
                f_i1 <= f_i1 + {{(ACC_W-2){din[1]}}, din};
                f_i2 <= f_i2 + f_i1;
                f_i3 <= f_i3 + f_i2;
                p_i1 <= p_i1 + {{(ACC_W-2){din[1]}}, din};
                p_i2 <= p_i2 + p_i1;
                p_i3 <= p_i3 + p_i2;

                if (f_cnt == osr_fast - 1) begin
                    f_cnt <= 16'd0;
                    f_z1 <= f_i3;
                    f_z2 <= f_c1;
                    f_z3 <= f_c2;
                    data_fast <= f_c3[31:0];
                    count_fast <= count_fast + 32'd1;
                    fast_strobe <= 1'b1;
                end else
                    f_cnt <= f_cnt + 16'd1;

                if (p_cnt == osr_prec - 1) begin
                    p_cnt <= 16'd0;
                    p_z1 <= p_i3;
                    p_z2 <= p_c1;
                    p_z3 <= p_c2;
                    data_prec <= p_c3[31:0];
                    count_prec <= count_prec + 32'd1;
                    prec_strobe <= 1'b1;
                end else
                    p_cnt <= p_cnt + 16'd1;
            end
        end
    end

endmodule

`default_nettype wire
